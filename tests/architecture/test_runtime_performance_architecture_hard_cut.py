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


def test_opennews_rest_poster_uses_async_http_contract_without_isawaitable_fallback() -> None:
    client = _read("src/parallax/integrations/news_feeds/opennews_client.py")
    init_source = client.split("def __init__", 1)[1].split("\n    def fetch", 1)[0]
    fetch_rest_source = client.split("async def _fetch_rest_entries", 1)[1].split(
        "\n\nasync def _default_post_json",
        1,
    )[0]
    forbidden_tokens = (
        "from inspect import isawaitable",
        "isawaitable(",
        "payload_result = await payload_result",
        "post_json: Callable[..., Any]",
    )
    violations = [token for token in forbidden_tokens if token in client]

    assert violations == []
    assert "class _OpenNewsPostJson(Protocol)" in client
    assert (
        "def __call__(self, url: str, *, token: str, body: Mapping[str, Any]) -> Awaitable[Mapping[str, Any]]"
    ) in client
    assert "post_json: _OpenNewsPostJson | None = None" in init_source
    assert "payload_result = await self._post_json(" in fetch_rest_source


def test_opennews_rest_fetch_bridge_uses_formal_coroutine_close_contract_without_optional_probe() -> None:
    client = _read("src/parallax/integrations/news_feeds/opennews_client.py")
    bridge_source = client.split("def _run_rest_fetch", 1)[1].split("\n\ndef _source_fetch_policy", 1)[0]
    forbidden_tokens = (
        "def _run_rest_fetch(coro: Any)",
        'getattr(coro, "close", None)',
        "close = getattr",
        "if callable(close)",
    )
    violations = [token for token in forbidden_tokens if token in bridge_source]

    assert violations == []
    assert "def _run_rest_fetch[ResultT](coro: Coroutine[Any, Any, ResultT]) -> ResultT:" in client
    assert "coro.close()" in bridge_source


def test_opennews_rest_fetch_policy_has_no_integration_local_defaults() -> None:
    client = _read("src/parallax/integrations/news_feeds/opennews_client.py")
    worker = _read("src/parallax/domains/news_intel/runtime/news_fetch_worker.py")
    forbidden_tokens = (
        "DEFAULT_REST_PAGE",
        "DEFAULT_REST_LIMIT",
        "DEFAULT_MAX_REST_PAGES",
        "DEFAULT_REST_OVERLAP_MS",
        "MIN_REST_OVERLAP_MS",
    )
    violations = [token for token in forbidden_tokens if token in client]

    assert violations == []
    assert "def _required_positive_int(value: Any, field_name: str) -> int:" in client
    assert 'raise ValueError(f"OpenNews REST fetch policy missing {field_name}")' in client
    assert '_fetch_policy_int(source, "overlap_ms")' not in worker


def test_provider_integration_numeric_boundaries_reject_runtime_repairs() -> None:
    gmgn_gateway = _read("src/parallax/integrations/gmgn/openapi_gateway.py")
    gmgn_client = _read("src/parallax/integrations/gmgn/openapi_client.py")
    feed_client = _read("src/parallax/integrations/news_feeds/feed_client.py")
    opennews_client = _read("src/parallax/integrations/news_feeds/opennews_client.py")
    cryptopanic_client = _read("src/parallax/integrations/news_feeds/cryptopanic_client.py")
    combined = "\n".join((gmgn_gateway, gmgn_client, feed_client, opennews_client, cryptopanic_client))
    forbidden_tokens = (
        "max(0, int(token_info_cache_ttl_seconds))",
        "max(1, int(retry_attempts))",
        "max(1, int(limit))",
        "max(1, int(max_attempts))",
        "max(1, int(page))",
        'max(1, int(_first(params, "max_items") or 50))',
    )

    assert [token for token in forbidden_tokens if token in combined] == []
    assert "gmgn_openapi_retry_attempts_required" in gmgn_gateway
    assert "gmgn_openapi_token_kline_limit_required" in gmgn_client
    assert "feed_client_max_attempts_required" in feed_client
    assert '"page": _required_positive_int(page, "page")' in opennews_client
    assert 'raise ValueError(f"OpenNews REST fetch policy invalid {field_name}")' in opennews_client
    assert '_required_positive_query_int(_first(params, "max_items"), field_name="max_items", default=50)' in (
        cryptopanic_client
    )
    assert 'raise ValueError(f"CryptoPanic feed URL invalid {field_name}")' in cryptopanic_client


def test_opennews_provider_signal_does_not_enter_fetch_brief_hot_path() -> None:
    fetch_worker = _read("src/parallax/domains/news_intel/runtime/news_fetch_worker.py")

    assert "news_item_agent_brief_eligibility" not in fetch_worker
    assert "brief_input" not in fetch_worker
    assert "NEWS_ITEM_AGENT_BRIEF_MAX_PUBLISHED_AGE_MS" not in fetch_worker
