from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NEWS_INTEL_ROOT = ROOT / "src/parallax/domains/news_intel"
ROUTES_NEWS = ROOT / "src/parallax/app/surfaces/api/routes_news.py"
OPENNEWS_CLIENT = ROOT / "src/parallax/integrations/news_feeds/opennews_client.py"
NEWS_PROVIDER_WIRING = ROOT / "src/parallax/app/runtime/provider_wiring/news.py"
NEWS_ARCHITECTURE = NEWS_INTEL_ROOT / "ARCHITECTURE.md"
AGENT_EXECUTION_DOC = ROOT / "docs/AGENT_EXECUTION.md"
NEWS_ITEM_RESEARCH_HARNESS_FILES = (
    NEWS_INTEL_ROOT / "services/news_item_brief_prompt_assembly.py",
    NEWS_INTEL_ROOT / "services/news_item_brief_stage.py",
    NEWS_INTEL_ROOT / "services/news_item_research_executor.py",
    NEWS_INTEL_ROOT / "services/news_item_research_policy.py",
    NEWS_INTEL_ROOT / "services/news_item_research_tools.py",
)

FORBIDDEN_IMPORTS = (
    "domains.token_intel.runtime",
    "domains.token_intel.services.token_radar_projection",
    "domains.pulse_lab",
    "domains.asset_market.runtime.market_tick",
)

FORBIDDEN_TABLE_REFERENCES = (
    "token_radar_rows",
    "token_radar_current_rows",
    "token_radar_rank_history",
    "token_radar_snapshot_audit",
    "pulse_candidates",
    "market_ticks",
)

FORBIDDEN_NEWS_RESEARCH_HARNESS_TOKENS = (
    "token_radar",
    "market_ticks",
    "pulse_candidates",
    "news_story_groups",
    "news_story_members",
    "news_context_items",
)

RAW_PROVIDER_PAYLOAD_OUTPUT_KEYS = (
    "provider_item_id",
    "raw_payload",
    "raw_payload_json",
    "provider_article_key",
    "provider_article_keys",
    "feed_url",
    "sync_cursor",
)

FORBIDDEN_ROUTE_TOKENS = (
    "NewsFetchWorker",
    "NewsItemProcessWorker",
    "feedparser",
    "resolve(",
    "extract_",
)


def _parse(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_call_name(node.value)}.{node.attr}"
    return ""


def _literal_strings(node: ast.AST) -> set[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return {node.value}
    strings: set[str] = set()
    for child in ast.iter_child_nodes(node):
        strings.update(_literal_strings(child))
    return strings


def _assigned_literal_strings_by_name(tree: ast.AST, names: set[str]) -> dict[str, set[str]]:
    strings_by_name: dict[str, set[str]] = {name: set() for name in names}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            target_names = {target.id for target in node.targets if isinstance(target, ast.Name)}
            for name in target_names & names:
                strings_by_name[name].update(_literal_strings(node.value))
            continue
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id in names
            and node.value is not None
        ):
            strings_by_name[node.target.id].update(_literal_strings(node.value))
    return strings_by_name


def test_news_intel_domain_exists_with_python_files() -> None:
    assert NEWS_INTEL_ROOT.exists()
    assert list(NEWS_INTEL_ROOT.rglob("*.py"))


def test_news_intel_does_not_import_runtime_or_projection_neighbors() -> None:
    for path in NEWS_INTEL_ROOT.rglob("*.py"):
        text = path.read_text()
        for forbidden in FORBIDDEN_IMPORTS:
            assert forbidden not in text, f"{path} imports forbidden boundary {forbidden}"


def test_news_intel_does_not_write_or_reference_other_read_models() -> None:
    for path in NEWS_INTEL_ROOT.rglob("*.py"):
        text = path.read_text()
        for forbidden in FORBIDDEN_TABLE_REFERENCES:
            assert forbidden not in text, f"{path} references forbidden table {forbidden}"


def test_news_local_research_harness_stays_news_local() -> None:
    for path in NEWS_ITEM_RESEARCH_HARNESS_FILES:
        text = path.read_text(encoding="utf-8")
        for forbidden in FORBIDDEN_NEWS_RESEARCH_HARNESS_TOKENS:
            assert forbidden not in text, f"{path} references forbidden harness token {forbidden}"


def test_news_item_brief_agent_stage_does_not_use_runtime_tools_keyword() -> None:
    violations: list[str] = []
    for path in NEWS_ITEM_RESEARCH_HARNESS_FILES:
        tree = _parse(path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if _call_name(node.func) != "AgentStageSpec":
                continue
            violations.extend(
                f"{path.relative_to(ROOT)}:{node.lineno} passes tools="
                for keyword in node.keywords
                if keyword.arg == "tools"
            )

    assert violations == []


def test_news_research_public_tool_outputs_exclude_raw_provider_payload_fields() -> None:
    executor = NEWS_INTEL_ROOT / "services/news_item_research_executor.py"
    output_keys_by_name = _assigned_literal_strings_by_name(
        _parse(executor),
        names={"_PUBLIC_ROW_KEYS_BY_TOOL", "_TARGET_CONTEXT_ITEM_PUBLIC_KEYS"},
    )
    for name, values in output_keys_by_name.items():
        assert values, f"{executor.relative_to(ROOT)} did not expose literal strings for {name}"

    output_keys = set().union(*output_keys_by_name.values())
    for forbidden in RAW_PROVIDER_PAYLOAD_OUTPUT_KEYS:
        assert forbidden not in output_keys, f"public tool output allowlist exposes {forbidden}"


def test_news_agent_docs_describe_local_research_harness_boundary() -> None:
    docs = "\n".join(
        [
            NEWS_ARCHITECTURE.read_text(encoding="utf-8"),
            AGENT_EXECUTION_DOC.read_text(encoding="utf-8"),
        ]
    )

    expected_phrases = (
        "empty-plan synthesis",
        "deterministic research policy",
        "local read-only tool executor",
        "There is no shared runtime tool loop",
        "Tools are input evidence, not business facts",
        "Host deterministic policy and read-only tool executor are News-local harness",
    )
    for phrase in expected_phrases:
        assert phrase in docs


def test_news_routes_stay_read_only_when_present() -> None:
    if not ROUTES_NEWS.exists():
        return

    text = ROUTES_NEWS.read_text()
    for forbidden in FORBIDDEN_ROUTE_TOKENS:
        assert forbidden not in text, f"{ROUTES_NEWS} contains write-side token {forbidden}"


def test_opennews_runtime_has_no_short_lived_websocket_fetch_path() -> None:
    forbidden_tokens = (
        "DEFAULT_OPENNEWS_WSS_URL",
        "news.subscribe",
        "news.unsubscribe",
        "_entry_from_message",
        "_fetch_mode",
        "_default_connect",
        "websockets.connect",
        "status_code=101",
    )
    combined = "\n".join(path.read_text() for path in (OPENNEWS_CLIENT, NEWS_PROVIDER_WIRING))

    for forbidden in forbidden_tokens:
        assert forbidden not in combined


def test_news_reliability_docs_pin_opennews_rest_only_worker_contract() -> None:
    text = " ".join((ROOT / "docs/RELIABILITY.md").read_text().split())

    assert "OpenNews provider ingestion is REST-only" in text
    assert "must not open short-lived WebSocket subscribe cycles" in text
    assert "separate provider input path" in text
