from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "parallax"
AGENT_EXECUTION = SRC / "platform" / "agent_execution.py"
MODEL_EXECUTION_PROVIDER_WIRING = SRC / "app" / "runtime" / "provider_wiring" / "model_execution.py"
MODEL_EXECUTION = SRC / "integrations" / "model_execution"
GATEWAY_FILES = {
    MODEL_EXECUTION / "execution_gateway.py",
    MODEL_EXECUTION / "structured_json_strategy.py",
}

pytestmark = pytest.mark.architecture


def _py_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.py") if "__pycache__" not in path.parts)


def _parse(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _imported_modules(tree: ast.AST) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def _import_aliases(tree: ast.AST) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                local_name = alias.asname or alias.name.split(".", maxsplit=1)[0]
                aliases[local_name] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                if alias.name == "*":
                    continue
                local_name = alias.asname or alias.name
                aliases[local_name] = f"{node.module}.{alias.name}"
    return aliases


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Subscript):
        return _call_name(node.value)
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_call_name(node.value)}.{node.attr}"
    return ""


def _call_leaf(node: ast.AST) -> str:
    if isinstance(node, ast.Subscript):
        return _call_leaf(node.value)
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _resolved_call_name(node: ast.AST, aliases: dict[str, str]) -> str:
    name = _call_name(node)
    base, separator, rest = name.partition(".")
    if base not in aliases:
        return name
    return f"{aliases[base]}{separator}{rest}" if separator else aliases[base]


def test_litellm_sdk_execution_only_in_gateway() -> None:
    violations: list[str] = []
    for path in _py_files(MODEL_EXECUTION):
        if path in GATEWAY_FILES:
            continue
        tree = _parse(path)
        aliases = _import_aliases(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                resolved_name = _resolved_call_name(node.func, aliases)
                if resolved_name in {"litellm.acompletion", "litellm.completion"}:
                    violations.append(f"{path.relative_to(ROOT)}:{node.lineno} calls {resolved_name}")

    assert violations == []


def test_litellm_completion_called_only_by_structured_json_strategy() -> None:
    allowlist = {MODEL_EXECUTION / "structured_json_strategy.py"}
    violations: list[str] = []
    for path in _py_files(SRC):
        if path in allowlist:
            continue
        tree = _parse(path)
        aliases = _import_aliases(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            resolved_name = _resolved_call_name(node.func, aliases)
            if resolved_name in {"litellm.acompletion", "litellm.completion"}:
                violations.append(f"{path.relative_to(ROOT)}:{node.lineno} calls {resolved_name}")

    assert violations == []


def test_agent_execution_gateway_does_not_import_domain_repositories() -> None:
    gateway = MODEL_EXECUTION / "execution_gateway.py"
    if not gateway.exists():
        raise AssertionError("agent_execution_gateway.py must exist")
    imports = _imported_modules(_parse(gateway))
    violations = sorted(module for module in imports if ".repositories" in module or module.endswith(".repositories"))
    assert violations == []


def test_domain_packages_do_not_import_litellm_sdk() -> None:
    domain_root = SRC / "domains"
    forbidden_prefixes = ("agents", "agents.", "openai", "litellm")
    violations: list[str] = []
    for path in _py_files(domain_root):
        imports = _imported_modules(_parse(path))
        violations.extend(
            f"{path.relative_to(ROOT)} imports {module}"
            for module in sorted(imports)
            if module.startswith(forbidden_prefixes)
        )

    assert violations == []


def test_watchlist_summary_agent_client_stays_removed() -> None:
    path = MODEL_EXECUTION / "watchlist_summary_agent_client.py"
    assert not path.exists()


def test_agent_execution_types_have_single_live_source() -> None:
    stale = MODEL_EXECUTION / "agent_execution_types.py"
    assert not stale.exists()


def test_agent_capacity_reservation_release_is_sync_contract_without_awaitable_fallback() -> None:
    source = AGENT_EXECUTION.read_text(encoding="utf-8")
    reservation_source = source.split("class AgentCapacityReservation", 1)[1].split("\n\n__all__", 1)[0]
    forbidden_tokens = (
        "ReleaseCallback = Callable[[], None | Awaitable[None]]",
        "await result",
        "Awaitable[None]]",
    )
    violations = [token for token in forbidden_tokens if token in source]

    assert violations == []
    assert "ReleaseCallback = Callable[[], None]" in source
    assert "result = release()" in reservation_source
    assert "agent_capacity_release_must_be_sync" in reservation_source


def test_agent_hashing_has_single_live_source() -> None:
    stale = MODEL_EXECUTION / "agent_hashing.py"
    assert not stale.exists()


def test_agent_model_selection_is_worker_runtime_owned() -> None:
    settings_text = (SRC / "platform" / "config" / "settings.py").read_text(encoding="utf-8")
    agent_execution_text = (SRC / "platform" / "agent_execution.py").read_text(encoding="utf-8")
    config_example = (ROOT / "config.example.yaml").read_text(encoding="utf-8")

    for forbidden in (
        "watchlist_handle_summary_model",
        "narrative_intel_model",
        "news_item_brief_model",
    ):
        assert forbidden not in settings_text
        assert forbidden not in config_example

    agent_stage_spec_text = agent_execution_text.partition("class AgentStageSpec")[2].partition(
        "class AgentExecutionRequestAudit"
    )[0]
    assert "model: str" not in agent_stage_spec_text
    assert "agent_runtime:" in settings_text
    assert "defaults:" in settings_text


def test_news_item_brief_has_no_runtime_legacy_hash_fallback() -> None:
    forbidden = (
        "legacy_hash",
        "legacy input_hash",
        "request_json.packet",
        "historical packet",
        "old_hash",
    )
    paths = [
        "src/parallax/domains/news_intel/runtime/news_item_brief_worker.py",
        "src/parallax/domains/news_intel/services/news_item_brief_input.py",
    ]
    for path in paths:
        text = Path(path).read_text(encoding="utf-8")
        lowered = text.lower()
        for token in forbidden:
            assert token not in lowered, f"{path} contains runtime compatibility token {token!r}"


def test_agent_execution_numeric_boundaries_reject_instead_of_repair() -> None:
    gateway_source = (MODEL_EXECUTION / "execution_gateway.py").read_text(encoding="utf-8")
    structured_source = (MODEL_EXECUTION / "structured_json_strategy.py").read_text(encoding="utf-8")
    forbidden_gateway = (
        "rate_unit_count = max(1, int(rate_units))",
        "requested_units = max(1, int(requested_rate_units))",
        'int(audit_extra.get("safety_net_retries") or 0)',
    )
    forbidden_structured = ("attempts = max(1, int(context.capability_profile.client_validation_retries) + 1)",)

    assert [token for token in forbidden_gateway if token in gateway_source] == []
    assert [token for token in forbidden_structured if token in structured_source] == []
    assert "agent_execution_rate_units_required" in gateway_source
    assert "agent_execution_safety_net_retries_required" in gateway_source
    assert "def _safety_net_retries" in gateway_source
    assert "structured_json_client_validation_retries_required" in structured_source


def test_agent_execution_gateway_requires_formal_llm_gateway_surface_without_reflection_defaults() -> None:
    gateway_source = (MODEL_EXECUTION / "execution_gateway.py").read_text(encoding="utf-8")
    forbidden_tokens = (
        'getattr(llm_gateway, "trace_export_enabled", False)',
        'getattr(llm_gateway, "api_key", "")',
        'getattr(llm_gateway, "base_url", "")',
    )
    required_tokens = (
        "agent_execution_llm_gateway_api_key_required",
        "agent_execution_llm_gateway_base_url_required",
        "agent_execution_llm_gateway_trace_export_enabled_required",
        "def _llm_gateway_text",
        "def _llm_gateway_bool",
    )

    assert [token for token in forbidden_tokens if token in gateway_source] == []
    assert [token for token in required_tokens if token not in gateway_source] == []


def test_news_canonical_merge_does_not_rewrite_agent_outputs() -> None:
    repository_text = (SRC / "domains/news_intel/repositories/news_repository.py").read_text(encoding="utf-8")

    forbidden_tokens = (
        "_remap_item_scoped_agent_outputs_to_news_item",
        "news_item_remap_reason",
        "UPDATE news_item_agent_runs",
    )
    assert [token for token in forbidden_tokens if token in repository_text] == []


def test_news_agent_gateway_has_one_demand_gate_without_lane_configuration_aliases() -> None:
    settings_source = (SRC / "platform/config/settings.py").read_text(encoding="utf-8")
    bootstrap_source = (SRC / "app/runtime/bootstrap.py").read_text(encoding="utf-8")
    provider_source = (SRC / "app/runtime/provider_wiring/__init__.py").read_text(encoding="utf-8")
    factory_source = (SRC / "app/runtime/worker_factories/news_intel.py").read_text(encoding="utf-8")
    combined = "\n".join((settings_source, bootstrap_source, provider_source, factory_source))

    assert "news_item_brief_configured" not in combined
    assert "news_story_brief_configured" not in combined
    assert "if settings.news_agent_execution_enabled:" in bootstrap_source
    assert "if settings.news_agent_execution_enabled" in provider_source
    assert factory_source.count("if not ctx.settings.llm_configured:") == 2
