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


def test_news_provider_contract_validation_uses_static_contract_not_provider_object() -> None:
    worker = _read("src/parallax/domains/news_intel/runtime/news_fetch_worker.py")
    runtime_app = _read("src/parallax/app/runtime/app.py")
    runtime_contract = _function_source("src/parallax/app/runtime/app.py", "_news_provider_contract_payload")
    provider_wiring = _read("src/parallax/app/runtime/provider_wiring/news.py")

    forbidden = {
        "src/parallax/domains/news_intel/runtime/news_fetch_worker.py": (
            "_supported_provider_types(self.feed_client)",
            "def _supported_provider_types(",
            'getattr(feed_client, "supported_provider_types"',
            'getattr(feed_client, "_registry"',
        ),
        "src/parallax/app/runtime/app.py": ("def _news_supported_provider_types(",),
        "src/parallax/app/runtime/app.py:_news_provider_contract_payload": (
            'getattr(runtime, "providers"',
            'getattr(getattr(runtime.settings, "news_intel", None), "sources", ())',
            'getattr(runtime.settings, "news_intel", None)',
            "runtime.providers",
            "feed_client",
            'getattr(feed_client, "_registry"',
            "supported_news_provider_types()",
        ),
        "src/parallax/app/runtime/provider_wiring/news.py": (
            "def supported_provider_types(",
            "self._registry.supported_provider_types()",
        ),
    }
    sources = {
        "src/parallax/domains/news_intel/runtime/news_fetch_worker.py": worker,
        "src/parallax/app/runtime/app.py": runtime_app,
        "src/parallax/app/runtime/app.py:_news_provider_contract_payload": runtime_contract,
        "src/parallax/app/runtime/provider_wiring/news.py": provider_wiring,
    }

    offenders = [
        f"{path} contains {token}" for path, tokens in forbidden.items() for token in tokens if token in sources[path]
    ]

    assert "RUNTIME_SUPPORTED_NEWS_PROVIDER_TYPES" in worker
    assert "RUNTIME_SUPPORTED_NEWS_PROVIDER_TYPES" in runtime_app
    assert "configured_sources = tuple(runtime.settings.news_intel.sources or ())" in runtime_contract
    assert offenders == []


def test_news_provider_contract_schema_uses_db_constraint_without_enum_fallback() -> None:
    worker = _read("src/parallax/domains/news_intel/runtime/news_fetch_worker.py")

    forbidden = (
        "from parallax.domains.news_intel.types.source_classification import PROVIDER_TYPES",
        "def _schema_provider_types(",
        "return tuple(PROVIDER_TYPES)",
    )
    required = (
        "repos.news.news_source_provider_constraint_values()",
        "schema_provider_types=",
    )

    assert [token for token in forbidden if token in worker] == []
    assert [token for token in required if token not in worker] == []


def test_news_item_process_agent_admission_context_uses_repository_readback_without_memory_fallback() -> None:
    worker = _read("src/parallax/domains/news_intel/runtime/news_item_process_worker.py")

    forbidden = (
        "fallback_item",
        "fallback_entities",
        "fallback_token_mentions",
        "fallback_fact_candidates",
        'row.setdefault("item"',
        'row.setdefault("entities"',
        'row.setdefault("token_mentions"',
        'row.setdefault("fact_candidates"',
    )
    required = (
        "load_agent_admission_contexts(",
        "_agent_admission_context(",
    )

    assert [token for token in forbidden if token in worker] == []
    assert [token for token in required if token not in worker] == []


def test_news_item_process_claim_attempt_and_lease_owner_require_claim_fields_without_defaults() -> None:
    worker_path = "src/parallax/domains/news_intel/runtime/news_item_process_worker.py"
    attempt_helper = _function_source(worker_path, "_processing_attempts")
    lease_helper = _function_source(worker_path, "_processing_lease_owner")

    forbidden_attempt_tokens = (
        'item.get("processing_attempts", 0)',
        'item.get("processing_attempts") or 0',
        "return 0",
        "max(0,",
    )
    forbidden_lease_tokens = (
        'item.get("processing_lease_owner") or ""',
        "return str(item.get",
    )

    assert [token for token in forbidden_attempt_tokens if token in attempt_helper] == []
    assert [token for token in forbidden_lease_tokens if token in lease_helper] == []
    assert 'item["processing_attempts"]' in attempt_helper
    assert "news_item_process_claim_attempt_required" in attempt_helper
    assert 'item["processing_lease_owner"]' in lease_helper
    assert "news_item_process_claim_lease_owner_required" in lease_helper


def test_news_current_item_payload_writes_require_domain_objects_without_mapping_or_alias_defaults() -> None:
    repository_path = "src/parallax/domains/news_intel/repositories/news_repository.py"
    worker_path = "src/parallax/domains/news_intel/runtime/news_item_process_worker.py"
    repository = _read(repository_path)
    worker_helper = _function_source(worker_path, "_strict_current_payload")
    agent_admission_payload = _function_source(repository_path, "_agent_admission_payload")
    write_functions = {
        name: _function_source(repository_path, name)
        for name in (
            "update_item_market_scope_and_story_identity",
            "update_item_market_scope_and_agent_admission",
            "update_item_agent_admission",
        )
    }

    assert "def _strict_current_dataclass_or_mapping_payload" not in repository
    assert "def _agent_admission_payload(value: NewsItemAgentAdmission)" in agent_admission_payload
    assert "if not isinstance(value, NewsItemAgentAdmission):" in agent_admission_payload

    forbidden_in_write_functions = (
        "Mapping[str, object]",
        "admission: Any",
    )
    write_offenders = [
        f"{name} contains {token}"
        for name, source in write_functions.items()
        for token in forbidden_in_write_functions
        if token in source
    ]

    forbidden_in_current_helpers = (
        "isinstance(value, Mapping)",
        'getattr(value, "to_payload", None)',
        "_object_payload(value)",
        "agent_representative_news_item_id",
        "representative_item_id",
        "or NEWS_ITEM_AGENT_ADMISSION_VERSION",
        'or "needs_review"',
        'status in {"eligible", "eligible_refresh"}',
    )
    helper_sources = {
        "worker._strict_current_payload": worker_helper,
        "repository._agent_admission_payload": agent_admission_payload,
    }
    helper_offenders = [
        f"{name} contains {token}"
        for name, source in helper_sources.items()
        for token in forbidden_in_current_helpers
        if token in source
    ]

    assert write_offenders == []
    assert helper_offenders == []


def test_news_current_fact_payload_helpers_have_no_reflective_object_fallbacks() -> None:
    repository_path = "src/parallax/domains/news_intel/repositories/news_repository.py"
    worker_path = "src/parallax/domains/news_intel/runtime/news_item_process_worker.py"
    repository_source = _read(repository_path)
    repository_helpers = {
        name: _function_source(repository_path, name)
        for name in ("_entity_payload", "_mention_payload", "_fact_payload")
    }
    worker_object_payload = _function_source(worker_path, "_object_payload")

    assert (
        "from parallax.domains.news_intel.types.news_extraction import NewsEntity, NewsFactCandidate, NewsTokenMention"
    ) in repository_source
    assert "from parallax.domains.news_intel.services.news_entity_extraction import NewsEntity" not in repository_source
    assert (
        "from parallax.domains.news_intel.services.news_token_mentions import NewsTokenMention" not in repository_source
    )
    assert (
        "from parallax.domains.news_intel.services.news_fact_candidates import NewsFactCandidate"
        not in repository_source
    )
    assert "isinstance(entity, NewsEntity)" in repository_helpers["_entity_payload"]
    assert "isinstance(mention, NewsTokenMention)" in repository_helpers["_mention_payload"]
    assert "isinstance(candidate, NewsFactCandidate)" in repository_helpers["_fact_payload"]

    forbidden = (
        'getattr(value, "model_dump"',
        "dump()",
        "vars(value)",
        'hasattr(value, "__dict__")',
        'getattr(value, "__dict__"',
        'getattr(value, "__slots__"',
        "hasattr(value, name)",
    )
    helper_offenders = [
        f"{name} contains {token}"
        for name, source in {**repository_helpers, "worker._object_payload": worker_object_payload}.items()
        for token in forbidden
        if token in source
    ]

    assert helper_offenders == []


def test_news_fetch_dirty_targets_use_repository_affected_items_without_fallback() -> None:
    worker = _read("src/parallax/domains/news_intel/runtime/news_fetch_worker.py")

    forbidden = (
        "fallback_news_item_id",
        "item_ids = [str(fallback",
    )
    required = (
        "affected_news_item_ids",
        "_affected_news_item_ids(news)",
        "if not item_ids:",
        "raise ValueError(",
    )

    assert [token for token in forbidden if token in worker] == []
    assert [token for token in required if token not in worker] == []


def test_news_projection_work_requires_repository_servable_filter_without_fallback() -> None:
    source = _read("src/parallax/domains/news_intel/runtime/news_projection_work.py")
    function_source = _function_source(
        "src/parallax/domains/news_intel/runtime/news_projection_work.py",
        "_servable_news_item_ids",
    )

    forbidden = (
        'getattr(repos, "news", None)',
        'getattr(news_repo, "servable_news_item_ids", None)',
        "if not callable(servable):",
        "return item_ids",
    )
    required = (
        "repos.news.servable_news_item_ids(item_ids)",
        "raise ValueError(",
    )

    assert "_servable_news_item_ids(repos, news_item_ids)" in source
    assert [token for token in forbidden if token in function_source] == []
    assert [token for token in required if token not in function_source] == []


def test_news_projection_workers_require_session_transaction_without_nullcontext_fallback() -> None:
    paths = [
        "src/parallax/domains/news_intel/runtime/news_page_projection_worker.py",
        "src/parallax/domains/news_intel/runtime/news_source_quality_projection_worker.py",
    ]
    sources = {path: _read(path) for path in paths}
    forbidden = (
        "from contextlib import nullcontext",
        "def _transaction(",
        'getattr(conn, "transaction", None)',
        "_transaction(repos.conn)",
        "return nullcontext()",
    )
    offenders = [
        f"{path} contains {token}" for path, source in sources.items() for token in forbidden if token in source
    ]

    assert offenders == []
    assert all("repos.transaction()" in source for source in sources.values())


def test_news_projection_dirty_target_terminal_paths_require_connection_transaction_without_nullcontext() -> None:
    path = "src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py"
    repository_text = _read(path)
    repository_tree = ast.parse(repository_text)
    transaction_helper = "\n".join(
        ast.get_source_segment(repository_text, node) or ""
        for node in ast.walk(repository_tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_transaction"
    )
    terminalize_source = _function_source(path, "terminalize_targets")

    repository_forbidden = (
        "from contextlib import nullcontext",
        "return nullcontext()",
    )
    terminalize_forbidden = (
        "nullcontext",
        "transaction_factory",
        "self.conn.commit()",
    )

    assert "raise RuntimeError" in transaction_helper
    assert "news_projection_dirty_target_transaction_required" in transaction_helper
    assert "with _transaction(self.conn):" in terminalize_source
    assert [token for token in repository_forbidden if token in repository_text] == []
    assert [token for token in terminalize_forbidden if token in terminalize_source] == []


def test_news_projection_dirty_target_mutations_use_connection_transaction_without_manual_commit_fallback() -> None:
    path = "src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py"
    repository_text = _read(path)
    mutation_sources = {
        name: _function_source(path, name)
        for name in (
            "enqueue_targets",
            "claim_due",
            "mark_done",
            "mark_error",
        )
    }
    forbidden = (
        "self.conn.commit()",
        'getattr(self.conn, "transaction", None)',
        "return nullcontext()",
    )

    assert "def _run_repository_write" in repository_text
    assert [token for token in forbidden if token in repository_text] == []
    assert all("_run_repository_write(self.conn, commit," in source for source in mutation_sources.values())


def test_news_projection_dirty_target_completion_keys_require_claim_attempt_contract() -> None:
    path = "src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py"
    repository_text = _read(path)
    key_records_source = _function_source(path, "_key_records")
    attempt_helper_source = _function_source(path, "_completion_attempt_count")
    forbidden = (
        'int(key.get("attempt_count") or 0)',
        'key.get("attempt_count") or 0',
    )

    assert [token for token in forbidden if token in key_records_source] == []
    assert "news projection dirty target completion requires attempt_count" in attempt_helper_source
    assert 'key["attempt_count"]' in attempt_helper_source
    assert "_completion_attempt_count(key)" in key_records_source
    assert "_key_records(keys)" in repository_text


def test_news_projection_dirty_completion_counts_require_real_cursor_rowcount() -> None:
    path = "src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py"
    repository_text = _read(path)
    mark_done_source = _function_source(path, "mark_done")
    mark_error_source = _function_source(path, "mark_error")
    forbidden = (
        'getattr(cursor, "rowcount", 0)',
        'int(getattr(cursor, "rowcount", 0) or 0)',
    )

    assert [token for token in forbidden if token in mark_done_source + mark_error_source] == []
    assert "def _cursor_rowcount(cursor: Any) -> int:" in repository_text
    assert "news_projection_dirty_target_rowcount_required" in repository_text
    assert "news_projection_dirty_target_rowcount_invalid" in repository_text
    assert "return _cursor_rowcount(cursor)" in mark_done_source
    assert "return _cursor_rowcount(cursor)" in mark_error_source


def test_news_projection_dirty_terminal_returning_counts_require_cursor_rowcount_match() -> None:
    path = "src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py"
    repository_text = _read(path)
    terminalize_source = _function_source(path, "terminalize_targets")
    delete_source = _function_source(path, "_delete_claimed_target_rows")
    helper_source = _function_source(path, "_returned_rowcount")
    forbidden = (
        "return len(deleted_records)",
        "return len(rows)",
        "deleted_count = len(rows)",
    )

    assert [token for token in forbidden if token in terminalize_source + delete_source] == []
    assert "def _returned_rowcount(cursor: Any, rows: list[Any]) -> int:" in repository_text
    assert "count = _cursor_rowcount(cursor)" in helper_source
    assert "if count != len(rows):" in helper_source
    assert "news_projection_dirty_target_rowcount_invalid" in helper_source
    assert "cursor = self.conn.execute" in delete_source
    assert "rows = cursor.fetchall()" in delete_source
    assert "deleted_count = _returned_rowcount(cursor, rows)" in delete_source
    assert "return [dict(row) for row in rows], deleted_count" in delete_source
    assert "deleted_records, deleted_count = self._delete_claimed_target_rows(records)" in terminalize_source
    assert "return deleted_count" in terminalize_source


def test_news_projection_dirty_claim_due_returning_rows_require_cursor_rowcount_match() -> None:
    path = "src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py"
    repository_text = _read(path)
    claim_source = _function_source(path, "claim_due")
    helper_source = _function_source(path, "_returned_rowcount")
    forbidden = (
        ").fetchall()",
        "return [dict(row) for row in rows]",
        "claimed_count = len(rows)",
        'getattr(cursor, "rowcount", 0)',
        "cursor.rowcount or 0",
    )

    assert [token for token in forbidden if token in claim_source] == []
    assert "def _returned_rowcount(cursor: Any, rows: list[Any]) -> int:" in repository_text
    assert "count = _cursor_rowcount(cursor)" in helper_source
    assert "if count != len(rows):" in helper_source
    assert "news_projection_dirty_target_rowcount_invalid" in helper_source
    assert "cursor = self.conn.execute" in claim_source
    assert "FOR UPDATE SKIP LOCKED" in claim_source
    assert "UPDATE news_projection_dirty_targets" in claim_source
    assert "RETURNING news_projection_dirty_targets.*" in claim_source
    assert "rows = cursor.fetchall()" in claim_source
    assert "_returned_rowcount(cursor, rows)" in claim_source
    assert "claimed_rows = [dict(row) for row in rows]" in claim_source
    assert "return claimed_rows" in claim_source


def test_news_projection_dirty_enqueue_counts_require_real_cursor_rowcount_without_candidate_count() -> None:
    path = "src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py"
    enqueue_source = _function_source(path, "enqueue_targets")
    forbidden = (
        'getattr(cursor, "rowcount", 0)',
        'int(getattr(cursor, "rowcount", 0) or 0)',
        "return len(records)",
    )

    assert [token for token in forbidden if token in enqueue_source] == []
    assert "cursor = self.conn.execute" in enqueue_source
    assert "return _cursor_rowcount(cursor)" in enqueue_source


def test_news_projection_dirty_source_watermarks_have_no_zero_or_runtime_fallback() -> None:
    repository_path = "src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py"
    work_path = "src/parallax/domains/news_intel/runtime/news_projection_work.py"
    worker_path = "src/parallax/domains/news_intel/runtime/news_source_quality_projection_worker.py"
    ops_path = "src/parallax/app/runtime/projection_dirty_targets.py"
    repository_text = _read(repository_path)
    dirty_records_source = _function_source(repository_path, "_dirty_records")
    work_text = _read(work_path)
    ops_text = _read(ops_path)
    future_targets_source = _function_source(worker_path, "_future_source_quality_targets")
    forbidden = (
        'row.get("source_watermark_ms") or 0',
        'int(row.get("source_watermark_ms") or 0)',
        "source_watermark_ms = 0",
    )

    assert "news_projection_dirty_target_source_watermark_required" in repository_text
    assert "news_projection_dirty_target_source_watermark_required" in work_text
    assert "ops_news_projection_dirty_source_watermark_required" in ops_text
    assert [token for token in forbidden if token in repository_text] == []
    assert [token for token in forbidden if token in dirty_records_source] == []
    assert [token for token in forbidden if token in work_text] == []
    assert [token for token in forbidden if token in ops_text] == []
    assert 'row.get("computed_at_ms") or now_ms' not in future_targets_source
    assert '"latest_item_published_at_ms"' in future_targets_source


def test_news_repository_write_counts_require_real_cursor_rowcount_without_defaults() -> None:
    path = "src/parallax/domains/news_intel/repositories/news_repository.py"
    repository_text = _read(path)
    count_functions = {
        "mark_item_processed",
        "mark_news_items_for_reprocessing",
        "update_item_market_scope_and_agent_admission",
        "update_item_agent_admission",
        "mark_item_process_retryable",
        "mark_item_process_terminal_failed",
        "release_expired_processing_items",
        "replace_source_quality_rows",
        "replace_page_rows_for_items",
        "replace_page_rows_for_story_targets",
        "delete_page_rows_for_sources",
        "delete_page_rows_without_enabled_observation_edges",
    }
    count_sources = {function_name: _function_source(path, function_name) for function_name in count_functions}
    forbidden = (
        'getattr(cursor, "rowcount", 0)',
        'int(getattr(cursor, "rowcount", 0) or 0)',
        "int(cursor.rowcount or 0)",
        "cursor.rowcount or 0",
    )

    violations = {
        function_name: [token for token in forbidden if token in source]
        for function_name, source in count_sources.items()
    }

    assert violations == {function_name: [] for function_name in count_functions}
    assert "def _cursor_rowcount(cursor: Any) -> int:" in repository_text
    assert "news_repository_rowcount_required" in repository_text
    assert "news_repository_rowcount_invalid" in repository_text
    for function_name, source in count_sources.items():
        assert "_cursor_rowcount(cursor)" in source, function_name


def test_news_repository_disable_unconfigured_returning_counts_require_cursor_rowcount_match() -> None:
    path = "src/parallax/domains/news_intel/repositories/news_repository.py"
    repository_text = _read(path)
    rows_source = _function_source(path, "_disable_unconfigured_source_rows")
    public_rows_source = _function_source(path, "disable_unconfigured_source_rows")
    count_source = _function_source(path, "disable_unconfigured_sources")
    helper_source = _function_source(path, "_returned_rowcount")
    forbidden = (
        "return len(rows)",
        "disabled_count = len(rows)",
    )

    assert [token for token in forbidden if token in rows_source + public_rows_source + count_source] == []
    assert "def _returned_rowcount(cursor: Any, rows: list[Any]) -> int:" in repository_text
    assert "count = _cursor_rowcount(cursor)" in helper_source
    assert "if count != len(rows):" in helper_source
    assert "news_repository_rowcount_invalid" in helper_source
    assert "cursor = self.conn.execute" in rows_source
    assert "rows = cursor.fetchall()" in rows_source
    assert "disabled_count = _returned_rowcount(cursor, rows)" in rows_source
    assert 'return [{**dict(row), "status": "disabled"} for row in rows], disabled_count' in rows_source
    assert "rows, _disabled_count = self._disable_unconfigured_source_rows(" in public_rows_source
    assert "return rows" in public_rows_source
    assert "_disabled_rows, disabled_count = self._disable_unconfigured_source_rows(" in count_source
    assert "return disabled_count" in count_source


def test_news_repository_claim_due_sources_returning_counts_require_cursor_rowcount_match() -> None:
    path = "src/parallax/domains/news_intel/repositories/news_repository.py"
    repository_text = _read(path)
    claim_source = _function_source(path, "claim_due_sources")
    helper_source = _function_source(path, "_returned_rowcount")
    forbidden = (
        ").fetchall()",
        "return len(rows)",
        "claimed_count = len(rows)",
        'getattr(cursor, "rowcount", 0)',
        "cursor.rowcount or 0",
    )

    assert [token for token in forbidden if token in claim_source] == []
    assert "def _returned_rowcount(cursor: Any, rows: list[Any]) -> int:" in repository_text
    assert "count = _cursor_rowcount(cursor)" in helper_source
    assert "if count != len(rows):" in helper_source
    assert "news_repository_rowcount_invalid" in helper_source
    assert "cursor = self.conn.execute" in claim_source
    assert "rows = cursor.fetchall()" in claim_source
    assert "_returned_rowcount(cursor, rows)" in claim_source
    assert "return [dict(row) for row in rows]" in claim_source


def test_news_source_upsert_returning_row_requires_cursor_rowcount_match() -> None:
    path = "src/parallax/domains/news_intel/repositories/news_repository.py"
    repository_text = _read(path)
    upsert_source = _function_source(path, "upsert_source")
    write_source = upsert_source[upsert_source.index("INSERT INTO news_sources") :]
    helper_source = _function_source(path, "_required_returning_row")
    forbidden = (
        ").fetchone()",
        'return {**dict(row), "status": status}',
        "return {**dict(row), 'status': status}",
        'getattr(cursor, "rowcount", 0)',
        "cursor.rowcount or 0",
    )

    assert [token for token in forbidden if token in write_source] == []
    assert "def _required_returning_row(cursor: Any, row: Any | None) -> dict[str, Any]:" in repository_text
    assert "returned_row = _optional_returning_row(cursor, row)" in helper_source
    assert 'raise TypeError("news_repository_rowcount_invalid")' in helper_source
    assert "cursor = self.conn.execute" in upsert_source
    assert "row = cursor.fetchone()" in upsert_source
    assert "returned_row = _required_returning_row(cursor, row)" in upsert_source
    assert "INSERT INTO news_sources" in upsert_source
    assert "RETURNING *" in upsert_source
    assert 'return {**returned_row, "status": status}' in upsert_source


def test_news_provider_item_upsert_returning_row_requires_cursor_rowcount_match() -> None:
    path = "src/parallax/domains/news_intel/repositories/news_repository.py"
    repository_text = _read(path)
    upsert_source = _function_source(path, "upsert_provider_item")
    write_source = upsert_source[upsert_source.index("INSERT INTO news_provider_items") :]
    helper_source = _function_source(path, "_required_returning_row")
    forbidden = (
        ").fetchone()",
        'return {**dict(row), "status": status',
        "return {**dict(row), 'status': status",
        'getattr(cursor, "rowcount", 0)',
        "cursor.rowcount or 0",
    )

    assert [token for token in forbidden if token in write_source] == []
    assert "def _required_returning_row(cursor: Any, row: Any | None) -> dict[str, Any]:" in repository_text
    assert "returned_row = _optional_returning_row(cursor, row)" in helper_source
    assert 'raise TypeError("news_repository_rowcount_invalid")' in helper_source
    assert "cursor = self.conn.execute" in upsert_source
    assert "row = cursor.fetchone()" in upsert_source
    assert "returned_row = _required_returning_row(cursor, row)" in upsert_source
    assert "INSERT INTO news_provider_items" in upsert_source
    assert "RETURNING *" in upsert_source
    assert (
        'return {**returned_row, "status": status, "incoming_provider_payload_status": incoming_payload_status}'
    ) in upsert_source


def test_news_canonical_item_upsert_returning_row_requires_cursor_rowcount_match() -> None:
    path = "src/parallax/domains/news_intel/repositories/news_repository.py"
    repository_text = _read(path)
    upsert_source = _function_source(path, "upsert_canonical_news_item")
    insert_start = upsert_source.index("INSERT INTO news_items")
    cursor_start = upsert_source.rindex("cursor = self.conn.execute", 0, insert_start)
    write_source = upsert_source[cursor_start : upsert_source.index("edge_evidence =")]
    helper_source = _function_source(path, "_required_returning_row")
    forbidden = (
        ").fetchone()",
        'getattr(cursor, "rowcount", 0)',
        "cursor.rowcount or 0",
    )

    assert [token for token in forbidden if token in write_source] == []
    assert "def _required_returning_row(cursor: Any, row: Any | None) -> dict[str, Any]:" in repository_text
    assert "returned_row = _optional_returning_row(cursor, row)" in helper_source
    assert 'raise TypeError("news_repository_rowcount_invalid")' in helper_source
    assert "cursor = self.conn.execute" in write_source
    assert "row = cursor.fetchone()" in write_source
    assert "returned_row = _required_returning_row(cursor, row)" in write_source
    assert "INSERT INTO news_items" in write_source
    assert "RETURNING *" in write_source
    assert 'str(returned_row["news_item_id"])' in upsert_source


def test_news_observation_edge_upsert_requires_cursor_rowcount_match() -> None:
    path = "src/parallax/domains/news_intel/repositories/news_repository.py"
    repository_text = _read(path)
    upsert_source = _function_source(path, "upsert_canonical_news_item")
    insert_start = upsert_source.index("INSERT INTO news_item_observation_edges")
    cursor_start = upsert_source.rindex("cursor = self.conn.execute", 0, insert_start)
    write_source = upsert_source[cursor_start : upsert_source.index("provider_article_remapped_old_item_ids")]
    helper_source = _function_source(path, "_required_rowcount")
    forbidden = (
        '\n        self.conn.execute(\n            """\n            INSERT INTO news_item_observation_edges',
        'getattr(cursor, "rowcount", 0)',
        "cursor.rowcount or 0",
    )

    assert [token for token in forbidden if token in write_source] == []
    assert "def _required_rowcount(cursor: Any, *, expected: int) -> int:" in repository_text
    assert "count = _cursor_rowcount(cursor)" in helper_source
    assert 'raise TypeError("news_repository_rowcount_invalid")' in helper_source
    assert "cursor = self.conn.execute" in write_source
    assert "INSERT INTO news_item_observation_edges" in write_source
    assert "_required_rowcount(cursor, expected=1)" in write_source


def test_news_observation_summary_refresh_requires_returning_rowcount_without_select_fallback() -> None:
    path = "src/parallax/domains/news_intel/repositories/news_repository.py"
    repository_text = _read(path)
    summary_source = _function_source(path, "_refresh_news_item_observation_summary")
    helper_source = _function_source(path, "_required_returning_row")
    optional_helper_source = _function_source(path, "_optional_returning_row")
    forbidden = (
        ").fetchone()",
        "SELECT * FROM news_items WHERE news_item_id",
        "return dict(fallback)",
        "return dict(row) if row is not None else {}",
        'getattr(cursor, "rowcount", 0)',
        "cursor.rowcount or 0",
    )

    assert [token for token in forbidden if token in summary_source] == []
    assert "def _required_returning_row(cursor: Any, row: Any | None) -> dict[str, Any]:" in repository_text
    assert "def _optional_returning_row(cursor: Any, row: Any | None) -> dict[str, Any] | None:" in repository_text
    assert "returned_row = _optional_returning_row(cursor, row)" in helper_source
    assert "count = _cursor_rowcount(cursor)" in optional_helper_source
    assert 'raise TypeError("news_repository_rowcount_invalid")' in helper_source
    assert "cursor = self.conn.execute" in summary_source
    assert "UPDATE news_items AS items" in summary_source
    assert "RETURNING items.*" in summary_source
    assert "row = cursor.fetchone()" in summary_source
    assert "_required_returning_row(cursor, row)" in summary_source
    assert "_optional_returning_row(cursor, row)" in summary_source
    assert "required: bool = True" in summary_source


def test_news_reselect_representative_returning_row_requires_cursor_rowcount_match() -> None:
    path = "src/parallax/domains/news_intel/repositories/news_repository.py"
    repository_text = _read(path)
    reselect_source = _function_source(path, "_reselect_news_item_representative_from_edges")
    helper_source = _function_source(path, "_optional_returning_row")
    forbidden = (
        ").fetchone()",
        "return dict(row)",
        "return dict(row) if row is not None else {}",
        'getattr(cursor, "rowcount", 0)',
        "cursor.rowcount or 0",
    )

    assert [token for token in forbidden if token in reselect_source] == []
    assert "def _optional_returning_row(cursor: Any, row: Any | None) -> dict[str, Any] | None:" in repository_text
    assert "count = _cursor_rowcount(cursor)" in helper_source
    assert 'raise TypeError("news_repository_rowcount_invalid")' in helper_source
    assert "cursor = self.conn.execute" in reselect_source
    assert "WITH representative_edge AS" in reselect_source
    assert "UPDATE news_items AS items" in reselect_source
    assert "RETURNING items.*" in reselect_source
    assert "row = cursor.fetchone()" in reselect_source
    assert "returned_row = _optional_returning_row(cursor, row)" in reselect_source
    assert "return returned_row or {}" in reselect_source


def test_news_edge_remap_returning_counts_require_cursor_rowcount_match() -> None:
    path = "src/parallax/domains/news_intel/repositories/news_repository.py"
    material_source = _function_source(path, "_remap_material_duplicate_edges_to_news_item")
    provider_source = _function_source(path, "_remap_provider_article_edges_to_news_item")
    helper_source = _function_source(path, "_returned_rowcount")
    forbidden = (
        ").fetchall()",
        'getattr(cursor, "rowcount", 0)',
        "cursor.rowcount or 0",
        'return [str(row["old_news_item_id"]) for row in rows]',
    )

    for source in (material_source, provider_source):
        assert [token for token in forbidden if token in source] == []
        assert "cursor = self.conn.execute" in source
        assert "UPDATE news_item_observation_edges AS edges" in source
        assert "RETURNING remapped.old_news_item_id" in source
        assert "rows = cursor.fetchall()" in source
        assert "_returned_rowcount(cursor, rows)" in source

    assert "count = _cursor_rowcount(cursor)" in helper_source
    assert 'raise TypeError("news_repository_rowcount_invalid")' in helper_source


def test_news_agent_run_and_brief_returning_rows_require_cursor_rowcount_match() -> None:
    path = "src/parallax/domains/news_intel/repositories/news_repository.py"
    repository_text = _read(path)
    run_source = _function_source(path, "insert_news_item_agent_run")
    brief_source = _function_source(path, "upsert_news_item_agent_brief")
    helper_source = _function_source(path, "_required_returning_row")
    forbidden = (
        ").fetchone()",
        "return dict(row)",
        'getattr(cursor, "rowcount", 0)',
        "cursor.rowcount or 0",
    )

    for source in (run_source, brief_source):
        assert [token for token in forbidden if token in source] == []
        assert "cursor = self.conn.execute" in source
        assert "row = cursor.fetchone()" in source
        assert "returned_row = _required_returning_row(cursor, row)" in source
        assert "return returned_row" in source

    assert "INSERT INTO news_item_agent_runs" in run_source
    assert "INSERT INTO news_item_agent_briefs" in brief_source
    assert "def _required_returning_row(cursor: Any, row: Any | None) -> dict[str, Any]:" in repository_text
    assert "returned_row = _optional_returning_row(cursor, row)" in helper_source
    assert 'raise TypeError("news_repository_rowcount_invalid")' in helper_source


def test_news_fetch_run_finish_returning_row_requires_cursor_rowcount_match() -> None:
    path = "src/parallax/domains/news_intel/repositories/news_repository.py"
    repository_text = _read(path)
    finish_source = _function_source(path, "finish_fetch_run")
    helper_source = _function_source(path, "_required_returning_row")
    forbidden = (
        ").fetchone()",
        "return dict(row)",
        "if row is None:",
        'getattr(cursor, "rowcount", 0)',
        "cursor.rowcount or 0",
    )

    assert [token for token in forbidden if token in finish_source] == []
    assert "def _required_returning_row(cursor: Any, row: Any | None) -> dict[str, Any]:" in repository_text
    assert "returned_row = _optional_returning_row(cursor, row)" in helper_source
    assert 'raise TypeError("news_repository_rowcount_invalid")' in helper_source
    assert "cursor = self.conn.execute" in finish_source
    assert "row = cursor.fetchone()" in finish_source
    assert "returned_row = _required_returning_row(cursor, row)" in finish_source
    assert "UPDATE news_sources" in finish_source
    assert "return returned_row" in finish_source


def test_news_fetch_run_start_requires_insert_and_source_update_rowcounts() -> None:
    path = "src/parallax/domains/news_intel/repositories/news_repository.py"
    repository_text = _read(path)
    start_source = _function_source(path, "start_fetch_run")
    helper_source = _function_source(path, "_required_rowcount")
    forbidden = (
        '\n        self.conn.execute(\n            """\n            INSERT INTO news_fetch_runs',
        '\n        self.conn.execute(\n            """\n            UPDATE news_sources',
        'getattr(cursor, "rowcount", 0)',
        "cursor.rowcount or 0",
    )

    assert [token for token in forbidden if token in start_source] == []
    assert "def _required_rowcount(cursor: Any, *, expected: int) -> int:" in repository_text
    assert "count = _cursor_rowcount(cursor)" in helper_source
    assert 'raise TypeError("news_repository_rowcount_invalid")' in helper_source
    assert "cursor = self.conn.execute" in start_source
    assert "_required_rowcount(cursor, expected=1)" in start_source
    assert start_source.count("_required_rowcount(cursor, expected=1)") == 2
    assert "INSERT INTO news_fetch_runs" in start_source
    assert "UPDATE news_sources" in start_source
    assert "return fetch_run_id" in start_source


def test_news_claim_unprocessed_items_returning_rows_require_cursor_rowcount_match() -> None:
    path = "src/parallax/domains/news_intel/repositories/news_repository.py"
    claim_source = _function_source(path, "claim_unprocessed_items")
    helper_source = _function_source(path, "_returned_rowcount")
    forbidden = (
        ").fetchall()",
        "return [dict(row) for row in rows]",
        'getattr(cursor, "rowcount", 0)',
        "cursor.rowcount or 0",
    )

    assert [token for token in forbidden if token in claim_source] == []
    assert "cursor = self.conn.execute" in claim_source
    assert "WITH picked AS" in claim_source
    assert "UPDATE news_items AS items" in claim_source
    assert "RETURNING items.*" in claim_source
    assert "rows = cursor.fetchall()" in claim_source
    assert "_returned_rowcount(cursor, rows)" in claim_source
    assert "claimed_rows = [dict(row) for row in rows]" in claim_source
    assert "return claimed_rows" in claim_source
    assert "count = _cursor_rowcount(cursor)" in helper_source
    assert 'raise TypeError("news_repository_rowcount_invalid")' in helper_source


def test_news_repository_zero_edge_delete_requires_cursor_rowcount_match() -> None:
    path = "src/parallax/domains/news_intel/repositories/news_repository.py"
    delete_source = _function_source(path, "_delete_zero_edge_news_item")

    assert "cursor = self.conn.execute(" in delete_source
    assert "row = cursor.fetchone()" in delete_source
    assert "deleted_count = _returned_rowcount(cursor, rows)" in delete_source
    assert "return deleted_count > 0" in delete_source
    assert "return row is not None" not in delete_source


def test_news_page_row_returning_writes_require_cursor_rowcount_match() -> None:
    path = "src/parallax/domains/news_intel/repositories/news_repository.py"
    repository_text = _read(path)
    replace_source = _function_source(path, "replace_page_rows_for_items")
    helper_source = _function_source(path, "_optional_returning_row")

    forbidden = (
        "if returned is None:",
        'elif bool(returned["inserted"]):',
        'getattr(cursor, "rowcount", 0)',
        "cursor.rowcount or 0",
    )

    assert [token for token in forbidden if token in replace_source] == []
    assert "def _optional_returning_row(cursor: Any, row: Any | None) -> dict[str, Any] | None:" in repository_text
    assert "count = _cursor_rowcount(cursor)" in helper_source
    assert "if count not in (0, 1):" in helper_source
    assert "if count != (1 if row is not None else 0):" in helper_source
    assert "returned_row = _optional_returning_row(cursor, returned)" in replace_source
    assert "if returned_row is None:" in replace_source
    assert 'elif bool(returned_row["inserted"]):' in replace_source


def test_news_current_brief_schema_cleanup_returning_rows_require_cursor_rowcount_match() -> None:
    path = "src/parallax/domains/news_intel/repositories/news_repository.py"
    cleanup_source = _function_source(path, "clear_current_briefs_outside_schema")
    helper_source = _function_source(path, "_returned_rowcount")
    forbidden = (
        ").fetchall()",
        'return [str(row["news_item_id"]) for row in rows]',
        'getattr(cursor, "rowcount", 0)',
        "cursor.rowcount or 0",
    )

    assert [token for token in forbidden if token in cleanup_source] == []
    assert "cursor = self.conn.execute" in cleanup_source
    assert "DELETE FROM news_item_agent_briefs" in cleanup_source
    assert "RETURNING news_item_id" in cleanup_source
    assert "rows = cursor.fetchall()" in cleanup_source
    assert "_returned_rowcount(cursor, rows)" in cleanup_source
    assert 'cleared_ids = [str(row["news_item_id"]) for row in rows]' in cleanup_source
    assert "return cleared_ids" in cleanup_source
    assert "count = _cursor_rowcount(cursor)" in helper_source
    assert 'raise TypeError("news_repository_rowcount_invalid")' in helper_source


def test_news_repository_writes_use_connection_transaction_without_manual_commit_fallback() -> None:
    path = "src/parallax/domains/news_intel/repositories/news_repository.py"
    source = _read(path)
    assert "news_repository_transaction_required" in source
    assert "def _news_repository_transaction" in source
    assert "def _news_repository_write" in source
    banned = {
        "self.conn.commit()",
        "return nullcontext()",
        'getattr(self.conn, "transaction", None)',
    }
    offenders = sorted(token for token in banned if token in source)
    assert offenders == []
    write_functions = {
        "upsert_source",
        "reconcile_configured_sources",
        "disable_unconfigured_source_rows",
        "disable_unconfigured_sources",
        "claim_due_sources",
        "start_fetch_run",
        "finish_fetch_run",
        "update_source_http_cache",
        "update_source_sync_state",
        "upsert_provider_item",
        "upsert_canonical_news_item",
        "insert_news_item_agent_run",
        "upsert_news_item_agent_brief",
        "clear_current_briefs_outside_schema",
        "claim_unprocessed_items",
        "replace_item_entities",
        "replace_token_mentions",
        "replace_fact_candidates",
        "mark_item_processed",
        "mark_news_items_for_reprocessing",
        "update_item_content_classification",
        "update_item_market_scope_and_story_identity",
        "update_item_market_scope_and_agent_admission",
        "update_item_agent_admission",
        "mark_item_process_retryable",
        "mark_item_process_terminal_failed",
        "release_expired_processing_items",
        "replace_source_quality_rows",
        "replace_page_rows_for_items",
        "replace_page_rows_for_story_targets",
        "delete_page_rows_for_sources",
        "delete_page_rows_without_enabled_observation_edges",
    }
    missing = [
        function_name
        for function_name in sorted(write_functions)
        if f"@_news_repository_write\n    def {function_name}" not in source
    ]
    assert missing == []


def test_news_runtime_write_workers_require_session_transaction_without_conn_fallback() -> None:
    paths = [
        "src/parallax/domains/news_intel/runtime/news_fetch_worker.py",
        "src/parallax/domains/news_intel/runtime/news_item_process_worker.py",
        "src/parallax/domains/news_intel/runtime/news_item_brief_worker.py",
    ]
    sources = {path: _read(path) for path in paths}
    forbidden = (
        "repos.conn.transaction()",
        "with repos.conn.transaction()",
        "conn.transaction()",
    )
    offenders = [
        f"{path} contains {token}" for path, source in sources.items() for token in forbidden if token in source
    ]

    assert offenders == []
    assert all("repos.transaction()" in source for source in sources.values())


def test_ops_projection_dirty_repair_does_not_recompute_news_agent_admission() -> None:
    source = _read("src/parallax/app/runtime/projection_dirty_targets.py")
    forbidden = {
        "decide_news_item_agent_admission",
        "NewsItemAgentAdmissionContext",
        "load_agent_admission_contexts",
    }
    offenders = sorted(token for token in forbidden if token in source)
    assert offenders == []


def test_ops_projection_dirty_execute_requires_transaction_without_nullcontext_fallback() -> None:
    path = "src/parallax/app/runtime/projection_dirty_targets.py"
    enqueue_source = _function_source(path, "enqueue_projection_dirty_targets")
    transaction_source = _function_source(path, "_transaction")
    forbidden = (
        "return nullcontext()",
        'getattr(conn, "transaction", None)',
        "if transaction is None:",
    )

    assert "if execute else nullcontext()" in enqueue_source
    assert "raise RuntimeError" in transaction_source
    assert "projection_dirty_targets_transaction_required" in transaction_source
    assert [token for token in forbidden if token in transaction_source] == []


def test_ops_projection_dirty_repair_reads_minimal_news_item_keyset() -> None:
    path = "src/parallax/app/runtime/projection_dirty_targets.py"
    enqueue_source = _function_source(path, "_enqueue_news_targets")
    fetch_source = _function_source(path, "_fetch_news_item_rows")
    forbidden = (
        "JOIN news_sources",
        "LEFT JOIN LATERAL",
        "news_token_mentions",
        "news_fact_candidates",
        "content_classification_json",
        "agent_admission_json",
        "provider_signal_json",
        "provider_token_impacts_json",
    )

    assert "if news_item_projections" in enqueue_source
    assert "items.news_item_id" in fetch_source
    assert "items.published_at_ms AS source_watermark_ms" in fetch_source
    assert "items.agent_admission_status" in fetch_source
    assert [token for token in forbidden if token in fetch_source] == []


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


def test_news_item_brief_worker_uses_formal_audit_validation_and_admission_contracts_without_reflection() -> None:
    path = "src/parallax/domains/news_intel/runtime/news_item_brief_worker.py"
    source = _read(path)
    provider_error_audit = _function_source(path, "_provider_error_audit")
    audit_dict = _function_source(path, "_audit_dict")
    object_dict = _function_source(path, "_dict")
    admission_payload = _function_source(path, "_agent_admission_payload")

    forbidden = (
        "getattr(validation,",
        'getattr(audit, "model_dump"',
        'getattr(value, "model_dump"',
        'getattr(value, "__slots__"',
        "hasattr(value, name)",
        "is_dataclass",
        "asdict(",
        "def _object_payload",
    )

    assert [token for token in forbidden if token in source] == []
    assert "NewsItemBriefValidationResult" in source
    assert "AgentExecutionRequestAudit | AgentExecutionResultAudit" in provider_error_audit
    assert "news_item_brief_agent_error_audit_contract_required" in provider_error_audit
    assert "if not isinstance(value, Mapping):" in audit_dict
    assert "news_item_brief_agent_run_audit_contract_required" in audit_dict
    assert "return {}" in object_dict
    assert "if not isinstance(value, NewsItemAgentAdmission):" in admission_payload
    assert "news_item_brief_agent_admission_contract_required" in admission_payload


def test_news_item_brief_entity_support_uses_formal_entity_lane_contract_without_reflection() -> None:
    path = "src/parallax/domains/news_intel/services/news_item_brief_entity_support.py"
    source = _read(path)
    domain_source = _function_source(path, "_entity_lane_domains")

    forbidden = (
        "getattr(entity,",
        "getattr(target,",
        "hasattr(",
        'getattr(value, "model_dump"',
        'getattr(value, "__slots__"',
        "is_dataclass",
        "asdict(",
    )

    assert [token for token in forbidden if token in source] == []
    assert "NewsItemBriefEntityLane" in source
    assert "def _entity_lane_domains(entity: NewsItemBriefEntityLane)" in domain_source
    assert "entity.market_domain" in domain_source
    assert "entity.entity_type" in domain_source
    assert "entity.target_id" in domain_source
    assert "entity.candidate_targets" in domain_source


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


def test_opennews_provider_signal_is_not_news_agent_prompt_evidence_or_priority() -> None:
    paths = [
        "src/parallax/domains/news_intel/types/news_item_brief.py",
        "src/parallax/domains/news_intel/services/news_item_brief_input.py",
        "src/parallax/domains/news_intel/services/news_item_agent_policy.py",
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


def test_opennews_provider_signal_only_reaches_agent_admission_and_page_as_provider_rating() -> None:
    admission = _read("src/parallax/domains/news_intel/services/news_item_agent_admission.py")
    page_projection = _read("src/parallax/domains/news_intel/services/news_page_projection.py")
    notification_rules = _read("src/parallax/domains/notifications/services/notification_rules.py")

    assert "provider_rating" in admission
    assert "provider_signal_json" in admission
    assert "provider_score" not in admission
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
    offenders = [f"page projection contains {token}" for token in forbidden_everywhere if token in page_projection] + [
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


def test_news_detail_signal_fallback_helpers_are_removed() -> None:
    source = _read("src/parallax/domains/news_intel/repositories/news_repository.py")
    forbidden = {
        "def _signal_from_agent_brief",
        "def _projection_missing_signal",
        "def _direction_label",
        "projection_missing",
    }
    offenders = sorted(token for token in forbidden if token in source)
    assert offenders == []


def test_news_item_detail_requires_projected_page_row_contract_without_raw_item_fallbacks() -> None:
    source = _function_source(
        "src/parallax/domains/news_intel/repositories/news_repository.py",
        "get_news_item_detail",
    )
    helper_sources = "\n".join(
        _function_source("src/parallax/domains/news_intel/repositories/news_repository.py", function_name)
        for function_name in (
            "_required_projected_page_text",
            "_required_projected_page_mapping",
            "_required_projected_page_list",
        )
    )
    forbidden = {
        '_json_dict(projected.get("signal")) or _projection_missing_signal',
        'projected.get("representative_news_item_id") or item_payload.get("news_item_id")',
        'projected.get("story_key") or item_payload.get("story_key")',
        'projected.get("story") or item_payload.get("story_identity_json")',
        'projected.get("market_scope") or item_payload.get("market_scope_json") or {}',
        'projected.get("agent_admission_status") or item_payload.get("agent_admission_status") or "needs_review"',
        'projected.get("agent_admission_reason") or item_payload.get("agent_admission_reason") or ""',
        'projected.get("agent_admission") or item_payload.get("agent_admission_json") or {}',
        'or item_payload.get("agent_representative_news_item_id")',
        'or projected.get("representative_news_item_id")',
        'projected.get("content_class") or item_payload.get("content_class")',
    }
    offenders = sorted(token for token in forbidden if token in source)
    assert offenders == []
    for required in (
        "_required_projected_page_text(",
        "_required_projected_page_mapping(",
        "_required_projected_page_list(",
    ):
        assert required in source
    assert "news_item_detail_projection_required" in helper_sources
    assert "news_item_detail_projection_invalid" in helper_sources


def test_news_page_list_requires_projected_page_row_contract_without_public_defaults() -> None:
    source = "\n".join(
        _function_source("src/parallax/domains/news_intel/repositories/news_repository.py", function_name)
        for function_name in (
            "_list_projected_news_page_rows",
            "list_news_high_signal_notification_candidates",
        )
    )
    helper_sources = "\n".join(
        _function_source("src/parallax/domains/news_intel/repositories/news_repository.py", function_name)
        for function_name in (
            "_projected_news_page_row_payload",
            "_required_news_page_row_text",
            "_required_news_page_row_mapping",
            "_required_news_page_row_list",
        )
    )
    forbidden = {
        'payload["agent_brief"] = _public_agent_brief_payload(payload.get("agent_brief"))',
        "payloads.append(payload)",
    }
    offenders = sorted(token for token in forbidden if token in source)
    assert offenders == []
    assert "_projected_news_page_row_payload(" in source
    assert "news_page_row_projection_required" in helper_sources
    assert "news_page_row_projection_invalid" in helper_sources
    assert '_public_agent_brief_payload(_required_news_page_row_mapping(payload, "agent_brief"))' in helper_sources


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


def test_news_agent_provider_article_duplicate_lookup_uses_edges_not_jsonb_expansion() -> None:
    functions = [
        "load_agent_admission_contexts",
        "_agent_exact_duplicate_context",
    ]
    offenders: list[str] = []
    for function_name in functions:
        source = _function_source("src/parallax/domains/news_intel/repositories/news_repository.py", function_name)
        if "jsonb_array_elements_text" in source:
            offenders.append(f"{function_name} expands provider_article_keys_json")
    load_source = _function_source(
        "src/parallax/domains/news_intel/repositories/news_repository.py",
        "load_agent_admission_contexts",
    )
    assert "target_provider_edges" in load_source
    assert "duplicate_edges.provider_article_key = target_provider_edges.provider_article_key" in load_source
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


def test_news_item_brief_reused_run_identity_requires_run_id_without_empty_fallback() -> None:
    source = _read("src/parallax/domains/news_intel/runtime/news_item_brief_worker.py")
    forbidden = {
        'run_id=str(run.get("run_id") or "")',
        'failed_current_run_id=str(run.get("run_id") or "")',
        'source_run_id = str(source_run.get("run_id") or "")',
        'if not str(run.get("run_id") or ""):\n        return None',
    }

    assert sorted(token for token in forbidden if token in source) == []
    assert "news_item_brief_run_id_required" in source
    assert "_required_run_id(run, reason=" in source
    assert 'source_run_id = _required_run_id(run, reason="invalid_completed_source_run")' in source
    assert '"source_run_id": source_run_id' in source


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


def test_news_page_row_payload_requires_formal_json_sections_without_defaults() -> None:
    source = "\n".join(
        (
            _function_source(
                "src/parallax/domains/news_intel/repositories/news_repository.py",
                "_page_row_payload",
            ),
            _function_source(
                "src/parallax/domains/news_intel/repositories/news_repository.py",
                "_required_page_mapping",
            ),
            _function_source(
                "src/parallax/domains/news_intel/repositories/news_repository.py",
                "_required_page_list",
            ),
        )
    )
    required = {
        "_required_page_list(payload,",
        "_required_page_mapping(payload,",
        "news_page_row_payload_required",
        "news_page_row_payload_invalid",
    }
    forbidden = {
        'payload.get("token_lanes") or []',
        'payload.get("fact_lanes") or []',
        'payload.get("story") or {}',
        'payload.get("token_impacts") or []',
        'payload.get("content_tags") or []',
        'payload.get("content_classification") or {}',
        'payload.get("source") or {}',
        'payload.get("signal") or {}',
        'payload.get("provider_rating") or {}',
        'payload.get("agent_brief") or {"status": "pending"}',
        'payload.get("market_scope") or {}',
    }
    assert sorted(token for token in required if token not in source) == []
    assert sorted(token for token in forbidden if token in source) == []


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
