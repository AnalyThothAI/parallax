from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "parallax"
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


def test_agent_hashing_has_single_live_source() -> None:
    stale = MODEL_EXECUTION / "agent_hashing.py"
    assert not stale.exists()


def test_agent_model_selection_is_worker_runtime_owned() -> None:
    settings_text = (SRC / "platform" / "config" / "settings.py").read_text(encoding="utf-8")
    agent_execution_text = (SRC / "platform" / "agent_execution.py").read_text(encoding="utf-8")
    config_example = (ROOT / "config.example.yaml").read_text(encoding="utf-8")

    for forbidden in (
        "pulse_agent_model",
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


def test_pulse_agent_runtime_has_no_post_stage_tool_query_path() -> None:
    retired_query = SRC / "domains/pulse_lab/queries/agent_tool_queries.py"
    forbidden_tokens = (
        "fetch_evidence_event_urls",
        "enrich_evidence_urls",
        "agent_tool_queries",
    )
    offenders: list[str] = []
    for path in [
        SRC / "domains/pulse_lab/services/pulse_decision_runtime.py",
        SRC / "integrations/model_execution/pulse_decision_agent_client.py",
        SRC / "domains/pulse_lab/providers.py",
    ]:
        text = path.read_text(encoding="utf-8")
        offenders.extend(
            f"{path.relative_to(ROOT)} contains retired Pulse agent tool-query token {token}"
            for token in forbidden_tokens
            if token in text
        )

    assert not retired_query.exists()
    assert offenders == []


def test_pulse_decision_runtime_has_no_database_pool_dependency() -> None:
    runtime_text = (SRC / "domains/pulse_lab/services/pulse_decision_runtime.py").read_text(encoding="utf-8")
    wiring_text = (SRC / "app/runtime/provider_wiring/model_execution.py").read_text(encoding="utf-8")

    assert "db_pool" not in runtime_text
    assert "PulseDecisionRuntimeService(db_pool=" not in wiring_text
    assert "db_pool is required for LiteLLMPulseDecisionProvider" not in wiring_text


def test_pulse_final_decision_refs_are_not_synthesized_from_packet_inputs() -> None:
    normalization_text = (
        SRC / "domains/pulse_lab/services/agent_output_normalization.py"
    ).read_text(encoding="utf-8")

    forbidden_tokens = (
        "_synthesize_missing_supporting_refs",
        "_supporting_refs_from_event_ids",
        "_fallback_supporting_refs",
        "inserted_from_allowed_evidence_refs",
    )
    assert [token for token in forbidden_tokens if token in normalization_text] == []


def test_pulse_evidence_refs_have_no_fuzzy_or_alias_canonicalization() -> None:
    normalization_text = (
        SRC / "domains/pulse_lab/services/agent_output_normalization.py"
    ).read_text(encoding="utf-8")

    forbidden_tokens = (
        "unique_same_type_edit_distance_1",
        "ambiguous_same_type_edit_distance_1",
        "event_source_alias",
        "event_prefix_alias",
        "_bounded_levenshtein_distance",
        "_event_ref_alias",
    )
    assert [token for token in forbidden_tokens if token in normalization_text] == []


def test_pulse_runtime_manifest_uses_agent_runtime_language_not_committee_or_harness_language() -> None:
    runtime_text = (SRC / "domains/pulse_lab/services/agent_runtime.py").read_text(encoding="utf-8")

    forbidden_tokens = (
        "research_committee",
        "research-committee",
        '"closed_loop"',
    )
    assert [token for token in forbidden_tokens if token in runtime_text] == []


def test_pulse_finalization_has_no_post_stage_mutable_freshness_health_query() -> None:
    job_service_text = (
        SRC / "domains/pulse_lab/services/pulse_candidate_job_service.py"
    ).read_text(encoding="utf-8")

    forbidden_tokens = (
        "PulseFreshnessHealthService",
        "health_status=",
        '"publish_status":',
    )
    assert [token for token in forbidden_tokens if token in job_service_text] == []


def test_pulse_stage_audit_no_longer_dual_writes_safety_net_trace_metadata() -> None:
    client_text = (SRC / "integrations/model_execution/pulse_decision_agent_client.py").read_text(
        encoding="utf-8"
    )
    decision_types_text = (SRC / "domains/pulse_lab/types/agent_decision.py").read_text(encoding="utf-8")

    forbidden_client_tokens = (
        '"safety_net": safety',
        '"safety_net_used": safety',
        '"safety_net_retries": safety',
    )
    forbidden_type_tokens = (
        "dual-writing",
        "one release cycle",
    )

    assert [token for token in forbidden_client_tokens if token in client_text] == []
    assert [token for token in forbidden_type_tokens if token in decision_types_text] == []


def test_pulse_runtime_manifest_no_longer_advertises_safety_net_switch() -> None:
    paths = [
        SRC / "domains/pulse_lab/providers.py",
        SRC / "domains/pulse_lab/services/agent_runtime.py",
        SRC / "integrations/model_execution/pulse_decision_agent_client.py",
    ]
    offenders = [
        f"{path.relative_to(ROOT)} contains safety_net_enabled"
        for path in paths
        if "safety_net_enabled" in path.read_text(encoding="utf-8")
    ]

    assert offenders == []


def test_pulse_runtime_has_no_terminal_run_reuse_short_circuit() -> None:
    paths = [
        SRC / "domains/pulse_lab/services/pulse_agent_cost_guard.py",
        SRC / "domains/pulse_lab/services/pulse_candidate_job_service.py",
        SRC / "domains/pulse_lab/services/agent_eval.py",
        SRC / "domains/pulse_lab/repositories/pulse_runs_repository.py",
    ]
    forbidden_tokens = (
        "reuse_terminal_run",
        "terminal_fingerprint_found",
        "terminal_run_for_fingerprint",
        "reused_run_id",
    )
    offenders = [
        f"{path.relative_to(ROOT)} contains {token}"
        for path in paths
        for token in forbidden_tokens
        if token in path.read_text(encoding="utf-8")
    ]

    assert offenders == []


def test_pulse_runtime_uses_single_decision_lane() -> None:
    paths = [
        SRC / "platform/config/settings.py",
        SRC / "domains/pulse_lab/services/pulse_agent_cost_guard.py",
        SRC / "domains/pulse_lab/services/pulse_candidate_job_service.py",
        SRC / "domains/pulse_lab/runtime/pulse_candidate_worker.py",
        SRC / "integrations/model_execution/pulse_decision_agent_client.py",
        SRC / "app/runtime/provider_wiring/model_execution.py",
    ]
    forbidden_tokens = (
        "pulse.pipeline",
        "pulse.signal_analyst",
        "pulse.bear_case",
        "pulse.risk_portfolio_judge",
    )
    offenders = [
        f"{path.relative_to(ROOT)} contains {token}"
        for path in paths
        for token in forbidden_tokens
        if token in path.read_text(encoding="utf-8")
    ]

    assert offenders == []


def test_pulse_decision_lane_literal_lives_in_runtime_contract_only() -> None:
    paths = [
        path
        for path in SRC.rglob("*.py")
        if "src/parallax/platform/db/alembic/versions" not in str(path)
    ]
    offenders = [
        str(path.relative_to(ROOT))
        for path in paths
        if path != SRC / "platform/agent_execution.py"
        and '"pulse.decision"' in path.read_text(encoding="utf-8")
    ]

    assert offenders == []


def test_pulse_runtime_has_no_stage_plan_contract() -> None:
    paths = [
        SRC / "domains/pulse_lab/providers.py",
        SRC / "domains/pulse_lab/services/pulse_agent_cost_guard.py",
        SRC / "domains/pulse_lab/services/pulse_candidate_job_service.py",
        SRC / "domains/pulse_lab/services/agent_eval.py",
        SRC / "integrations/model_execution/pulse_decision_agent_client.py",
    ]
    forbidden_tokens = (
        "PulseStagePlan",
        "stage_plan",
        '"run_signal_analyst"',
        '"run_bear_case"',
        '"run_risk_portfolio_judge"',
        "run_signal_analyst=",
        "run_bear_case=",
        "run_risk_portfolio_judge=",
    )
    offenders = [
        f"{path.relative_to(ROOT)} contains {token}"
        for path in paths
        for token in forbidden_tokens
        if token in path.read_text(encoding="utf-8")
    ]

    assert offenders == []


def test_pulse_runtime_has_single_final_decision_stage_contract() -> None:
    paths = [
        SRC / "domains/pulse_lab/providers.py",
        SRC / "domains/pulse_lab/services/agent_runtime.py",
        SRC / "domains/pulse_lab/services/claim_evidence_verifier.py",
        SRC / "domains/pulse_lab/services/prompt_loader.py",
        SRC / "domains/pulse_lab/services/pulse_candidate_job_service.py",
        SRC / "domains/pulse_lab/services/pulse_decision_runtime.py",
        SRC / "domains/pulse_lab/types/agent_decision.py",
        SRC / "integrations/model_execution/pulse_decision_agent_client.py",
    ]
    forbidden_tokens = (
        "SignalAnalystMemo",
        "BearCaseMemo",
        "signal_memo",
        "bear_memo",
        "signal_analyst",
        "bear_case",
        "risk_portfolio_judge",
    )
    offenders = [
        f"{path.relative_to(ROOT)} contains {token}"
        for path in paths
        for token in forbidden_tokens
        if token in path.read_text(encoding="utf-8")
    ]

    assert offenders == []


def test_news_canonical_merge_does_not_rewrite_agent_outputs() -> None:
    repository_text = (SRC / "domains/news_intel/repositories/news_repository.py").read_text(encoding="utf-8")

    forbidden_tokens = (
        "_remap_item_scoped_agent_outputs_to_news_item",
        "news_item_remap_reason",
        "UPDATE news_item_agent_runs",
    )
    assert [token for token in forbidden_tokens if token in repository_text] == []
