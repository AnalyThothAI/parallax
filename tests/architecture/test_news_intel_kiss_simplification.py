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

RAW_PROJECTION_STRINGS = {"brief_input", "page", "source_quality", "story_brief"}
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


def test_news_fetch_worker_fetch_policy_requires_formal_jsonb_mapping_without_alias_or_string_repair() -> None:
    worker = _read("src/parallax/domains/news_intel/runtime/news_fetch_worker.py")
    fetch_policy_source = _function_source(
        "src/parallax/domains/news_intel/runtime/news_fetch_worker.py", "_fetch_policy_int"
    )
    required = {
        '_optional_fetch_policy_mapping(source.get("fetch_policy_json"), "fetch_policy_json")',
        'raise ValueError(f"news_fetch_{field_name}_required")',
    }
    forbidden = {
        "json.loads",
        "except json.JSONDecodeError",
        'source.get("fetch_policy")',
        "def _mapping(",
    }

    assert sorted(token for token in required if token not in worker) == []
    assert sorted(token for token in forbidden if token in worker) == []
    assert 'source.get("fetch_policy")' not in fetch_policy_source


def test_news_fetch_worker_cursor_scalars_have_no_zero_repair() -> None:
    path = "src/parallax/domains/news_intel/runtime/news_fetch_worker.py"
    high_watermark_source = _function_source(path, "_cursor_high_watermark_ms")
    overlap_source = _function_source(path, "_fetch_policy_overlap_ms")
    helper_source = _function_source(path, "_required_cursor_overlap_ms")
    combined = "\n".join((high_watermark_source, overlap_source, helper_source))
    required = {
        '"high_watermark_ms" not in cursor',
        'value = cursor["high_watermark_ms"]',
        'raise ValueError("news_fetch_cursor_high_watermark_ms_required")',
        "_required_cursor_overlap_ms(source_cursor)",
        'raise ValueError("news_fetch_cursor_overlap_ms_required")',
    }
    forbidden = {
        'cursor.get("high_watermark_ms") or 0',
        'source_cursor.get("overlap_ms") or 0',
        "return max(0, int(value or 0))",
    }

    assert sorted(token for token in required if token not in combined) == []
    assert sorted(token for token in forbidden if token in combined) == []


def test_opennews_source_fetch_policy_rejects_malformed_present_json_contract() -> None:
    source = _function_source("src/parallax/integrations/news_feeds/opennews_client.py", "_source_fetch_policy")
    required = {
        'raise ValueError("OpenNews fetch_policy_json must be a mapping")',
    }
    forbidden = {
        "json.loads",
        "except json.JSONDecodeError",
        "return dict(decoded)",
    }

    assert sorted(token for token in required if token not in source) == []
    assert sorted(token for token in forbidden if token in source) == []


def test_news_material_identity_rejects_provider_token_impacts_json_strings_without_repair() -> None:
    source = _read("src/parallax/domains/news_intel/types/news_material_identity.py")
    required = {
        'raise ValueError("news_material_identity_provider_token_impacts_json_required")',
    }
    forbidden = {
        "import json",
        "json.loads",
        "except json.JSONDecodeError",
    }

    assert sorted(token for token in required if token not in source) == []
    assert sorted(token for token in forbidden if token in source) == []


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


def test_news_item_process_agent_admission_context_rejects_malformed_present_shapes() -> None:
    source = _read("src/parallax/domains/news_intel/runtime/news_item_process_worker.py")
    compact_source = "".join(source.split())
    admission_source = _function_source(
        "src/parallax/domains/news_intel/runtime/news_item_process_worker.py",
        "_agent_admission_context",
    )
    required = {
        'raise ValueError(f"news_item_process_agent_admission_context_{field_name}_required:{news_item_id}")',
    }
    forbidden = {
        "import json",
        "json.loads",
        "except json.JSONDecodeError",
        "def _json_dict(",
        "def _json_list(",
        "def _list_of_dicts(",
        '_json_dict(context_payload["item"])',
        '_list_of_dicts(context_payload["token_mentions"])',
        '_list_of_dicts(context_payload.get("entities"))',
    }
    compact_required = {
        token.replace(" ", "")
        for token in (
            '_optional_item_process_mapping(item_payload.get("authority_scope_json"), "authority_scope_json"',
            '_required_agent_context_mapping(row["item"], "item", news_item_id=news_item_id',
            '_required_agent_context_mapping_list(row["entities"], "entities", news_item_id=news_item_id',
            '_required_agent_context_mapping_list(row["token_mentions"], "token_mentions", news_item_id=news_item_id',
            '_required_agent_context_mapping_list(row["fact_candidates"], "fact_candidates", news_item_id=news_item_id',
        )
    }

    assert sorted(token for token in required if token not in source) == []
    assert sorted(token for token in compact_required if token not in compact_source) == []
    assert sorted(token for token in forbidden if token in source) == []
    assert "_json_dict(" not in admission_source
    assert "_json_list(" not in admission_source


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
        'story_identity_payload.get("story_key") or ""',
        'story_identity_payload.get("version") or ""',
        'admission_payload.get("status") or ""',
        'admission_payload.get("reason") or ""',
        'admission_payload.get("version") or ""',
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


def test_news_fetch_run_finish_requires_explicit_counts_without_zero_repair() -> None:
    path = "src/parallax/domains/news_intel/repositories/news_repository.py"
    finish_source = _function_source(path, "finish_fetch_run")
    helper_source = "\n".join(
        _function_source(path, function_name)
        for function_name in (
            "_required_fetch_run_count",
            "_required_fetch_run_completion_status",
            "_required_fetch_run_finished_at_ms",
            "_optional_fetch_run_http_status",
            "_optional_fetch_run_extra_json",
        )
    )
    combined = "\n".join((finish_source, helper_source))
    required = {
        "_required_fetch_run_finished_at_ms(finished_at_ms)",
        "_required_fetch_run_completion_status(status)",
        '_required_fetch_run_count("fetched_count", fetched_count, items_seen)',
        '_required_fetch_run_count("inserted_count", inserted_count, items_inserted)',
        '_required_fetch_run_count("updated_count", updated_count, items_updated)',
        '_required_fetch_run_count("duplicate_count", duplicate_count)',
        "_optional_fetch_run_http_status(http_status)",
        "_optional_fetch_run_extra_json(extra_json)",
        'raise ValueError("news_fetch_run_status_required")',
        'raise ValueError("news_fetch_run_finished_at_ms_required")',
        'raise ValueError("news_fetch_run_http_status_required")',
        'raise ValueError("news_fetch_run_extra_json_required")',
        'raise ValueError(f"news_fetch_run_{field_name}_required")',
    }
    forbidden = {
        "_first_int(",
        "max(0, int(value))",
        "int(value or 0)",
        "int(finished_at_ms)",
        "int(http_status)",
        "_json(dict(extra_json or {}))",
        "return 0",
    }

    assert sorted(token for token in required if token not in combined) == []
    assert sorted(token for token in forbidden if token in combined) == []


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
    assert "_run_repository_write(self.conn, commit, _terminalize_targets)" in terminalize_source
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
    key_text_source = _function_source(path, "_completion_key_text")
    window_text_source = _function_source(path, "_completion_window_text")
    attempt_helper_source = _function_source(path, "_completion_attempt_count")
    forbidden = (
        'int(key.get("attempt_count") or 0)',
        'key.get("attempt_count") or 0',
        'str(key.get("projection_name") or "")',
        'str(key.get("target_kind") or "")',
        'str(key.get("target_id") or "")',
        'str(key.get("window") or "")',
        'key.get("window") or ""',
    )

    assert [token for token in forbidden if token in key_records_source] == []
    assert "news projection dirty target completion requires full target key from claim_due" in key_text_source
    assert "news projection dirty target completion requires window from claim_due" in window_text_source
    assert "news projection dirty target completion requires empty window from claim_due" in key_records_source
    assert '_completion_key_text(key, "projection_name")' in key_records_source
    assert '_completion_key_text(key, "target_kind")' in key_records_source
    assert '_completion_key_text(key, "target_id")' in key_records_source
    assert "_completion_window_text(key)" in key_records_source
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
    fetch_path = "src/parallax/domains/news_intel/runtime/news_fetch_worker.py"
    worker_path = "src/parallax/domains/news_intel/runtime/news_source_quality_projection_worker.py"
    ops_path = "src/parallax/app/runtime/projection_dirty_targets.py"
    news_repository_path = "src/parallax/domains/news_intel/repositories/news_repository.py"
    repository_text = _read(repository_path)
    news_repository_text = _read(news_repository_path)
    dirty_records_source = _function_source(repository_path, "_dirty_records")
    source_watermarks_for_sources_source = _function_source(
        news_repository_path,
        "list_news_item_source_watermarks_for_sources",
    )
    source_watermarks_source = _function_source(
        news_repository_path,
        "list_news_item_source_watermarks",
    )
    canonical_rebuild_source = _function_source(
        news_repository_path,
        "list_news_items_for_canonical_rebuild",
    )
    work_text = _read(work_path)
    fetch_text = _read(fetch_path)
    fetch_run_once_source = _function_source(fetch_path, "run_once_sync")
    fetch_persist_entries_source = _function_source(fetch_path, "_persist_entries")
    worker_text = _read(worker_path)
    worker_run_once_source = _function_source(worker_path, "run_once_sync")
    ops_text = _read(ops_path)
    future_targets_source = _function_source(worker_path, "_future_source_quality_targets")
    future_text_source = _function_source(worker_path, "_required_future_target_text")
    future_count_source = _function_source(worker_path, "_required_future_target_item_count")
    forbidden = (
        'row.get("source_watermark_ms") or 0',
        'int(row.get("source_watermark_ms") or 0)',
        'str(row.get("source_id") or "")',
        'str(row.get("window") or "")',
        'int(row.get("item_count") or 0)',
        'row.get("item_count") or 0',
        "source_watermark_ms = 0",
    )

    assert "news_projection_dirty_target_source_watermark_required" in repository_text
    assert "news_projection_dirty_target_source_watermark_required" in work_text
    assert "ops_news_projection_dirty_source_watermark_required" in ops_text
    assert [token for token in forbidden if token in repository_text] == []
    assert [token for token in forbidden if token in dirty_records_source] == []
    assert "_required_positive_news_item_source_watermark(" in news_repository_text
    assert (
        '"source_watermark_ms": _required_positive_news_item_source_watermark(row)'
        in source_watermarks_for_sources_source
    )
    assert '"source_watermark_ms": _required_positive_news_item_source_watermark(row)' in source_watermarks_source
    assert '"source_watermark_ms": _required_positive_news_item_source_watermark(row)' in canonical_rebuild_source
    assert 'int(row["source_watermark_ms"] or 0)' not in news_repository_text
    assert [token for token in forbidden if token in work_text] == []
    assert [token for token in forbidden if token in worker_text] == []
    assert [token for token in forbidden if token in ops_text] == []
    assert "news_item_id: now" not in fetch_text
    assert "list_news_item_source_watermarks_for_sources" in fetch_run_once_source
    assert "source_watermark_ms_by_news_item_id=changed_item_watermarks" in fetch_run_once_source
    assert "list_news_item_source_watermarks(news_item_ids=dirty_news_item_ids)" in fetch_persist_entries_source
    assert "source_watermark_ms_by_news_item_id=dirty_item_watermarks" in fetch_persist_entries_source
    assert "{news_item_id: fetched_at_ms for news_item_id in dirty_news_item_ids}" not in fetch_persist_entries_source
    assert "str(news_item_id): now" not in worker_text
    assert "_page_dirty_watermarks_for_changed_sources(" in worker_run_once_source
    assert "source_watermark_ms_by_news_item_id=changed_item_watermarks" in worker_run_once_source
    assert 'row.get("computed_at_ms") or now_ms' not in future_targets_source
    assert '"latest_item_published_at_ms"' in future_targets_source
    assert '_required_future_target_text(row, "source_id")' in future_targets_source
    assert '_required_future_target_text(row, "window").lower()' in future_targets_source
    assert "_required_future_target_item_count(row)" in future_targets_source
    assert "news_source_quality_future_target_{field_name}_required" in future_text_source
    assert "news_source_quality_future_target_item_count_required" in future_count_source


def test_news_projection_dirty_enqueue_requires_target_identity_without_silent_drop() -> None:
    path = "src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py"
    dirty_records_source = _function_source(path, "_dirty_records")
    dirty_text_source = _function_source(path, "_dirty_record_text")
    dirty_window_source = _function_source(path, "_dirty_record_window")
    combined = "\n".join((dirty_records_source, dirty_text_source, dirty_window_source))

    required = {
        '_dirty_record_text(row, field="projection_name")',
        '_dirty_record_text(row, field="target_kind")',
        '_dirty_record_text(row, field="target_id")',
        "_dirty_record_window(row, projection_name=projection_name)",
        'f"news_projection_dirty_target_{field}_required"',
        "news_projection_dirty_target_window_empty_required",
    }
    forbidden = {
        'row.get("projection_name") or ""',
        'row.get("target_kind") or ""',
        'row.get("target_id") or ""',
        "if not projection_name or not target_kind or not target_id:\n            continue",
    }

    assert sorted(token for token in required if token not in combined) == []
    assert sorted(token for token in forbidden if token in dirty_records_source) == []


def test_news_projection_work_claim_helpers_require_claim_contract_without_filtering() -> None:
    path = "src/parallax/domains/news_intel/runtime/news_projection_work.py"
    target_ids_source = _function_source(path, "_target_ids")
    source_quality_windows_source = _function_source(path, "source_quality_claim_windows")
    claim_text_source = _function_source(path, "_require_claim_text")
    empty_window_source = _function_source(path, "_require_claim_empty_window")
    source_quality_window_source = _function_source(path, "_require_source_quality_claim_window")
    combined = "\n".join(
        (
            target_ids_source,
            source_quality_windows_source,
            claim_text_source,
            empty_window_source,
            source_quality_window_source,
        )
    )
    required = {
        '_require_claim_text(row, field="projection_name", expected=projection_name, error_prefix=error_prefix)',
        '_require_claim_text(row, field="target_kind", expected=target_kind, error_prefix=error_prefix)',
        '_require_claim_text(row, field="target_id", error_prefix=error_prefix)',
        "_require_claim_empty_window(row, error_prefix=error_prefix)",
        'field="projection_name"',
        "expected=SOURCE_QUALITY",
        'error_prefix="news_source_quality_projection_claim"',
        "_require_source_quality_claim_window(row)",
        'f"{error_prefix}_{field}_required"',
        'f"{error_prefix}_window_empty_required"',
        "news_source_quality_projection_claim_window_required",
    }
    forbidden = {
        'row.get("projection_name") or ""',
        'row.get("target_kind") or ""',
        'row.get("target_id") or ""',
        'row.get("window") or ""',
        "if str(row.get",
        "if source_id and resolved_window",
    }

    assert sorted(token for token in required if token not in combined) == []
    assert sorted(token for token in forbidden if token in target_ids_source + source_quality_windows_source) == []


def test_news_projection_dirty_priority_has_no_int_repair() -> None:
    repository_path = "src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py"
    work_path = "src/parallax/domains/news_intel/runtime/news_projection_work.py"
    work_text = _read(work_path)
    priority_value_source = _function_source(repository_path, "_priority_value")
    priority_for_key_source = _function_source(work_path, "_priority_for_key")
    combined = "\n".join((priority_value_source, priority_for_key_source))

    required = {
        "_priority_for_key(priorities, news_item_id)",
        "_priority_for_key(priorities, story_key)",
        "news_projection_dirty_target_priority_required",
        "not isinstance(value, int) or isinstance(value, bool)",
        "not isinstance(raw_priority, int) or isinstance(raw_priority, bool)",
    }
    forbidden = {
        "int(priorities[news_item_id])",
        "int(priorities[story_key])",
        "return int(str(raw_priority))",
        "str(raw_priority)",
    }

    assert sorted(token for token in required if token not in work_text + combined) == []
    assert sorted(token for token in forbidden if token in work_text + priority_value_source) == []


def test_news_projection_dirty_due_at_has_no_int_or_zero_default_repair() -> None:
    repository_path = "src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py"
    work_path = "src/parallax/domains/news_intel/runtime/news_projection_work.py"
    repository_text = _read(repository_path)
    work_text = _read(work_path)
    dirty_records_source = _function_source(repository_path, "_dirty_records")
    dirty_due_source = _function_source(repository_path, "_dirty_due_at_ms")
    required_due_source = _function_source(repository_path, "_required_dirty_due_at_ms")
    work_due_source = _function_source(work_path, "_optional_due_at_ms")
    combined = "\n".join((dirty_records_source, dirty_due_source, required_due_source, work_due_source))
    forbidden = {
        "default_due_at_ms=int(due_at_ms if due_at_ms is not None else now_ms)",
        'target_due_at_ms = int(row.get("due_at_ms") or default_due_at_ms)',
        'kwargs["due_at_ms"] = int(due_at_ms)',
        '"due_at_ms": int(due_at_ms)',
    }
    required = {
        "_required_dirty_due_at_ms(due_at_ms if due_at_ms is not None else now_ms)",
        "_dirty_due_at_ms(row, default_due_at_ms=default_due_at_ms)",
        "_optional_due_at_ms(due_at_ms)",
        "news_projection_dirty_target_due_at_ms_required",
        "not isinstance(value, int) or isinstance(value, bool) or value <= 0",
    }

    assert sorted(token for token in required if token not in repository_text + work_text + combined) == []
    assert sorted(token for token in forbidden if token in repository_text + work_text) == []


def test_news_page_projection_worker_requires_claim_contract_without_target_id_filtering() -> None:
    path = "src/parallax/domains/news_intel/runtime/news_page_projection_worker.py"
    source = _read(path)
    claim_ids_source = _function_source(path, "_required_page_claim_news_item_ids")
    claim_text_source = _function_source(path, "_require_claim_text")
    claim_window_source = _function_source(path, "_require_claim_empty_window")
    combined = "\n".join((claim_ids_source, claim_text_source, claim_window_source))

    required = {
        "_required_page_claim_news_item_ids(claimed)",
        "processed=len(claimed_ids)",
        '_require_claim_text(row, field="projection_name", expected=PAGE_PROJECTION)',
        '_require_claim_text(row, field="target_kind", expected="news_item")',
        "_require_claim_empty_window(row)",
        "news_page_projection_claim_window_empty_required",
        'f"news_page_projection_claim_{field}_required"',
    }
    forbidden = {
        "page_news_item_ids(claimed)",
        "processed=len(page_news_item_ids(claimed))",
    }

    assert sorted(token for token in required if token not in source + combined) == []
    assert sorted(token for token in forbidden if token in source) == []


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
    source_payload = _function_source(path, "_source_payload")
    policy_helper = _function_source(path, "_optional_news_source_policy_mapping")
    write_source = upsert_source[upsert_source.index("INSERT INTO news_sources") :]
    helper_source = _function_source(path, "_required_returning_row")
    forbidden = (
        ").fetchone()",
        'return {**dict(row), "status": status}',
        "return {**dict(row), 'status': status}",
        'getattr(cursor, "rowcount", 0)',
        "cursor.rowcount or 0",
    )
    policy_forbidden = (
        '"authority_scope_json": _json_dict(authority_scope)',
        '"fetch_policy_json": _json_dict(fetch_policy)',
        '"cost_policy_json": _json_dict(cost_policy)',
        'payload["authority_scope"] = _json_dict(payload.get("authority_scope"))',
        'payload["fetch_policy"] = _json_dict(payload.get("fetch_policy"))',
        'payload["cost_policy"] = _json_dict(payload.get("cost_policy"))',
    )

    assert [token for token in forbidden if token in write_source] == []
    assert [token for token in policy_forbidden if token in upsert_source] == []
    assert [token for token in policy_forbidden if token in source_payload] == []
    assert "def _required_returning_row(cursor: Any, row: Any | None) -> dict[str, Any]:" in repository_text
    assert "returned_row = _optional_returning_row(cursor, row)" in helper_source
    assert 'raise TypeError("news_repository_rowcount_invalid")' in helper_source
    assert '_optional_news_source_policy_mapping(authority_scope, "authority_scope")' in upsert_source
    assert '_optional_news_source_policy_mapping(fetch_policy, "fetch_policy")' in upsert_source
    assert '_optional_news_source_policy_mapping(cost_policy, "cost_policy")' in upsert_source
    assert '_optional_news_source_policy_mapping(payload.get("authority_scope"), "authority_scope")' in source_payload
    assert '_optional_news_source_policy_mapping(payload.get("fetch_policy"), "fetch_policy")' in source_payload
    assert '_optional_news_source_policy_mapping(payload.get("cost_policy"), "cost_policy")' in source_payload
    assert "news_source_{field_name}_required" in policy_helper
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


def test_news_current_policy_material_duplicate_diagnostics_reject_malformed_rows() -> None:
    path = "src/parallax/domains/news_intel/repositories/news_repository.py"
    source = _function_source(path, "_current_policy_material_duplicate_groups")
    cluster_source = _function_source(path, "_current_policy_matching_material_cluster")
    helper_sources = "\n".join(
        _function_source(path, function_name)
        for function_name in (
            "_required_current_policy_material_text",
            "_required_current_policy_material_positive_int",
            "_required_current_policy_material_impacts",
        )
    )
    required = {
        '_required_current_policy_material_text(row, "provider_type")',
        '_required_current_policy_material_text(row, "source_id")',
        '_required_current_policy_material_text(row, "news_item_id")',
        '_required_current_policy_material_text(row, "title")',
        '_required_current_policy_material_positive_int(row, "published_at_ms")',
        '_required_current_policy_material_impacts(row, "provider_token_impacts_json")',
        "news_dedup_current_policy_material_{field_name}_required",
        'row["published_at_ms"]',
        'row["material_symbols"]',
        'candidate["published_at_ms"]',
        'candidate["material_symbols"]',
    }
    forbidden = {
        'str(row.get("provider_type") or "").strip().lower()',
        'str(row.get("source_id") or "")',
        'str(row.get("news_item_id") or "")',
        'int(value.get("published_at_ms") or 0)',
        'int(row.get("published_at_ms") or 0)',
        'int(candidate.get("published_at_ms") or 0)',
        'row.get("material_symbols") or set()',
        'candidate.get("material_symbols") or set()',
    }
    combined = "\n".join((source, cluster_source, helper_sources))

    assert sorted(token for token in required if token not in combined) == []
    assert sorted(token for token in forbidden if token in combined) == []


def test_news_dedup_diagnostics_requires_summary_row_contract_without_defaults() -> None:
    path = "src/parallax/domains/news_intel/repositories/news_repository.py"
    source = _function_source(path, "news_dedup_diagnostics")
    helper_sources = "\n".join(
        _function_source(path, function_name)
        for function_name in (
            "_required_news_dedup_diagnostics_nonnegative_int",
            "_required_news_dedup_diagnostics_list",
            "_required_news_dedup_diagnostics_mapping",
        )
    )
    required = {
        '_required_news_dedup_diagnostics_nonnegative_int(row, "raw_observation_count")',
        '_required_news_dedup_diagnostics_nonnegative_int(row, "canonical_item_count")',
        '_required_news_dedup_diagnostics_nonnegative_int(row, "observation_edge_count")',
        '_required_news_dedup_diagnostics_nonnegative_int(row, "enabled_serving_row_count")',
        '_required_news_dedup_diagnostics_nonnegative_int(row, "disabled_serving_row_count")',
        '_required_news_dedup_diagnostics_nonnegative_int(row, "enabled_exact_content_visible_duplicate_excess")',
        '_required_news_dedup_diagnostics_list(row, "top_visible_content_duplicate_groups")',
        '_required_news_dedup_diagnostics_list(row, "top_visible_canonical_duplicate_groups")',
        '_required_news_dedup_diagnostics_mapping(row, "material_title_duplicate_groups")',
        '_required_news_dedup_diagnostics_mapping(row, "case_insensitive_url_duplicate_groups")',
        '_required_news_dedup_diagnostics_mapping(row, "preview_or_generic_url_rows")',
        '_required_news_dedup_diagnostics_mapping(row, "brief_input_risk")',
        '_required_news_dedup_diagnostics_list(row, "source_sync_diagnostics")',
        "news_dedup_diagnostics_{field_name}_required",
    }
    forbidden = {
        'int(row["raw_observation_count"] or 0)',
        'int(row["canonical_item_count"] or 0)',
        'int(row["observation_edge_count"] or 0)',
        'int(row["enabled_serving_row_count"] or 0)',
        'int(row["disabled_serving_row_count"] or 0)',
        'row["enabled_exact_content_visible_duplicate_excess"] or 0',
        '_json_list(row["top_visible_content_duplicate_groups"])',
        '_json_list(row["top_visible_canonical_duplicate_groups"])',
        '_json_dict(row["material_title_duplicate_groups"])',
        '_json_dict(row["case_insensitive_url_duplicate_groups"])',
        '_json_dict(row["preview_or_generic_url_rows"])',
        '_json_dict(row["brief_input_risk"])',
        '_json_list(row["source_sync_diagnostics"])',
    }

    combined = "\n".join((source, helper_sources))
    compact_combined = "".join(combined.split())
    assert (
        sorted(token for token in required if token not in combined and "".join(token.split()) not in compact_combined)
        == []
    )
    assert sorted(token for token in forbidden if token in source) == []


def test_news_item_aggregate_changed_requires_summary_contract_without_defaults() -> None:
    path = "src/parallax/domains/news_intel/repositories/news_repository.py"
    source = _function_source(path, "_news_item_aggregate_changed")
    helper_sources = "\n".join(
        _function_source(path, function_name)
        for function_name in (
            "_required_news_item_aggregate_nonnegative_int",
            "_required_news_item_aggregate_list",
        )
    )
    required = {
        '_required_news_item_aggregate_nonnegative_int(existing, "duplicate_observation_count")',
        '_required_news_item_aggregate_nonnegative_int(updated, "duplicate_observation_count")',
        '_required_news_item_aggregate_list(existing, "source_ids_json")',
        '_required_news_item_aggregate_list(updated, "source_ids_json")',
        '_required_news_item_aggregate_list(existing, "source_domains_json")',
        '_required_news_item_aggregate_list(updated, "source_domains_json")',
        '_required_news_item_aggregate_list(existing, "provider_article_keys_json")',
        '_required_news_item_aggregate_list(updated, "provider_article_keys_json")',
        "news_item_aggregate_{field_name}_required",
    }
    forbidden = {
        'int(existing.get("duplicate_observation_count") or 0)',
        'int(updated.get("duplicate_observation_count") or 0)',
        '_json_list(existing.get("source_ids_json"))',
        '_json_list(updated.get("source_ids_json"))',
        '_json_list(existing.get("source_domains_json"))',
        '_json_list(updated.get("source_domains_json"))',
        '_json_list(existing.get("provider_article_keys_json"))',
        '_json_list(updated.get("provider_article_keys_json"))',
    }
    combined = "\n".join((source, helper_sources))

    assert sorted(token for token in required if token not in combined) == []
    assert sorted(token for token in forbidden if token in source) == []


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


def test_news_story_agent_run_and_brief_returning_rows_require_cursor_rowcount_match() -> None:
    path = "src/parallax/domains/news_intel/repositories/news_repository.py"
    repository_text = _read(path)
    run_source = _function_source(path, "insert_news_story_agent_run")
    brief_source = _function_source(path, "upsert_news_story_agent_brief")
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

    assert "INSERT INTO news_story_agent_runs" in run_source
    assert "INSERT INTO news_story_agent_briefs" in brief_source
    assert "story_brief_key" in run_source
    assert "story_brief_key" in brief_source
    assert "def _required_returning_row(cursor: Any, row: Any | None) -> dict[str, Any]:" in repository_text
    assert "returned_row = _optional_returning_row(cursor, row)" in helper_source
    assert 'raise TypeError("news_repository_rowcount_invalid")' in helper_source


def test_news_agent_payloads_require_explicit_audit_json_inputs() -> None:
    path = "src/parallax/domains/news_intel/repositories/news_repository.py"
    item_run_source = _function_source(path, "_agent_run_payload")
    item_brief_source = _function_source(path, "_agent_brief_payload")
    story_run_source = _function_source(path, "_story_agent_run_payload")
    story_brief_source = _function_source(path, "_story_agent_brief_payload")
    publishable_summary_source = _function_source(path, "_agent_publishable_summary")
    member_ids_source = _function_source(path, "_member_news_item_ids")
    forbidden = (
        'payload.get("request_json") or {}',
        'payload.get("validation_errors_json") or []',
        'payload.get("trace_metadata_json") or {}',
        'payload.get("usage_json") or {}',
        'payload.get("brief_json") or {}',
        'payload.get("member_news_item_ids_json")',
        'payload.get("execution_started", False)',
        '_json_dict(agent_brief.get("brief_json"))',
        "_json_list(value)",
    )
    run_scalar_forbidden = (
        'payload.get("backend") or "litellm_sdk"',
        'payload.get("latency_ms") or 0',
    )

    combined = "\n".join(
        (
            item_run_source,
            item_brief_source,
            story_run_source,
            story_brief_source,
            publishable_summary_source,
            member_ids_source,
        )
    )
    assert [token for token in forbidden if token in combined] == []
    assert [token for token in run_scalar_forbidden if token in item_run_source] == []
    assert [token for token in run_scalar_forbidden if token in story_run_source] == []
    assert '_required_json_mapping(payload, "request_json", label="news item agent run payload")' in item_run_source
    assert 'label = "news item agent run payload"' in item_run_source
    assert '_required_payload_text(payload, "backend", label=label)' in item_run_source
    assert '_required_payload_nonnegative_int(payload, "latency_ms", label=label)' in item_run_source
    assert '_required_json_mapping(payload, "brief_json", label="news item agent brief payload")' in item_brief_source
    assert "_agent_publishable_summary(payload, brief_json=brief_json)" in item_brief_source
    assert 'label = "news story agent run payload"' in story_run_source
    assert '_required_json_mapping(payload, "request_json", label=label)' in story_run_source
    assert "_required_member_news_item_ids(payload, label=label)" in story_run_source
    assert '_required_payload_text(payload, "backend", label=label)' in story_run_source
    assert '_required_payload_nonnegative_int(payload, "latency_ms", label=label)' in story_run_source
    assert '_required_json_mapping(payload, "brief_json", label="news story agent brief payload")' in story_brief_source
    assert "_agent_publishable_summary(payload, brief_json=brief_json)" in story_brief_source
    assert '_required_member_news_item_ids(payload, label="news story agent brief payload")' in story_brief_source


def test_news_repository_agent_brief_publishable_summary_requires_current_summary_field() -> None:
    source = _function_source(
        "src/parallax/domains/news_intel/repositories/news_repository.py",
        "_agent_publishable_summary",
    )
    required = {
        'value = agent_brief.get("summary_zh")',
        'if value is None and "summary_zh" in brief_json:',
        'value = brief_json.get("summary_zh")',
        "isinstance(value, str)",
        "bool(value.strip())",
    }
    forbidden = {
        'agent_brief.get("market_read_zh")',
        'brief_json.get("market_read_zh")',
        'agent_brief.get("summary_zh") or',
        'brief_json.get("summary_zh") or',
        "market_read text",
    }

    assert sorted(token for token in required if token not in source) == []
    assert sorted(token for token in forbidden if token in source) == []


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
    eligible_source = _function_source(path, "_row_brief_eligible")
    fetch_source = _function_source(path, "_fetch_news_item_rows")
    story_targets_source = _function_source(path, "_story_brief_targets")
    contract_docs = {
        "docs/ARCHITECTURE.md": _read("docs/ARCHITECTURE.md"),
        "docs/WORKERS.md": _read("docs/WORKERS.md"),
        "src/parallax/domains/news_intel/ARCHITECTURE.md": _read("src/parallax/domains/news_intel/ARCHITECTURE.md"),
    }
    forbidden = (
        "JOIN news_sources",
        "LEFT JOIN LATERAL",
        "news_token_mentions",
        "news_fact_candidates",
        "content_classification_json",
        "items.agent_admission_status",
        "provider_signal_json",
        "provider_token_impacts_json",
    )

    assert "if news_item_projections" in enqueue_source
    assert "items.news_item_id" in fetch_source
    assert "items.story_key" in fetch_source
    assert "items.lifecycle_status = 'processed'" in fetch_source
    assert "items.story_key <> ''" in fetch_source
    assert "items.story_identity_version = %(story_identity_version)s" in fetch_source
    assert "NEWS_STORY_IDENTITY_VERSION" in fetch_source
    assert "items.fetched_at_ms" in fetch_source
    assert "source_watermark_ms" in fetch_source
    assert "items.agent_admission_json" in fetch_source
    assert '"story_brief"' in _read(path)
    assert '"brief_input"' not in _read(path)
    assert "enqueue_story_brief_work" in enqueue_source
    assert "enqueue_item_brief_work" not in enqueue_source
    assert "_news_item_story_key(row)" in story_targets_source
    assert "_news_item_source_watermark_ms(row)" in story_targets_source
    assert "agent_admission_status" not in eligible_source
    assert "_news_item_brief_priority(row) < 100" in eligible_source
    assert [token for token in forbidden if token in fetch_source] == []
    assert "formal `agent_admission_json`" in "\n".join(contract_docs.values())
    assert [
        f"{path} contains scalar repair wording"
        for path, source in contract_docs.items()
        for token in ("persisted agent-admission status", "admission-status columns")
        if token in source
    ] == []


def test_ops_news_canonical_rebuild_reads_current_servable_story_keyset() -> None:
    repository_source = _function_source(
        "src/parallax/domains/news_intel/repositories/news_repository.py",
        "list_news_items_for_canonical_rebuild",
    )
    ops_source = _function_source(
        "src/parallax/app/surfaces/cli/commands/ops.py",
        "_news_canonical_rebuild_targets",
    )
    forbidden = {
        "list_news_item_ids_for_canonical_rebuild",
        "_optional_news_canonical_rebuild_text",
        '"projection_name": "brief_input"',
    }
    required_repository = {
        "FROM news_items AS items",
        "items.lifecycle_status = 'processed'",
        "items.story_key <> ''",
        "items.story_identity_version = %s",
        "NEWS_STORY_IDENTITY_VERSION",
        "JOIN news_sources AS edge_sources ON edge_sources.source_id = edges.source_id",
        "edge_sources.enabled = true",
        "source_watermark_ms > 0",
    }
    required_ops = {
        '"projection_name": "page"',
        '"projection_name": "story_brief"',
        '_required_news_canonical_rebuild_text(row, "story_key")',
        "_required_news_canonical_rebuild_watermark(row)",
    }

    assert sorted(token for token in forbidden if token in repository_source + ops_source) == []
    assert sorted(token for token in required_repository if token not in repository_source) == []
    assert sorted(token for token in required_ops if token not in ops_source) == []


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


def test_news_brief_workers_do_not_restore_missing_output_hash_from_audit_payload() -> None:
    workers = {
        "item": _function_source(
            "src/parallax/domains/news_intel/runtime/news_item_brief_worker.py",
            "_insert_run",
        ),
        "story": _function_source(
            "src/parallax/domains/news_intel/runtime/news_story_brief_worker.py",
            "_insert_run",
        ),
    }
    required = "output_hash=output_hash,"
    forbidden = {
        'audit.get("output_hash")',
        "output_hash or",
    }

    missing = [
        f"{name} worker missing explicit output hash write"
        for name, source in workers.items()
        if required not in source
    ]
    offenders = [
        f"{name} worker contains {token}" for name, source in workers.items() for token in forbidden if token in source
    ]
    assert missing + offenders == []


def test_news_brief_validation_publishable_text_requires_current_summary_field() -> None:
    source = _function_source(
        "src/parallax/domains/news_intel/services/news_item_brief_validation.py",
        "_ready_publishable_text_errors",
    )
    required = {
        'payload.get("summary_zh")',
        "ready output requires summary_zh",
    }
    forbidden = {
        'payload.get("market_read_zh")',
        'payload.get("summary_zh") or',
        "summary_zh or market_read_zh",
    }

    assert sorted(token for token in required if token not in source) == []
    assert sorted(token for token in forbidden if token in source) == []


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


def test_news_has_only_item_and_story_brief_llm_lanes() -> None:
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
    assert sorted(lane_names) == ["news.item_brief", "news.story_brief"]


def test_old_item_outputs_are_audit_only_after_story_agent_hard_cut() -> None:
    repository_path = "src/parallax/domains/news_intel/repositories/news_repository.py"
    repository_source = _read(repository_path)
    page_item_loader_source = _function_source(repository_path, "load_items_for_page_projection")
    story_projection_source = _function_source(repository_path, "load_story_projection_payloads_for_items")
    story_current_source = _function_source(repository_path, "_current_story_agent_briefs_for_story_keys")
    source_quality_input_source = _function_source(repository_path, "_list_source_quality_inputs_for_source_ids")
    page_projection_source = _read("src/parallax/domains/news_intel/services/news_page_projection.py")
    agent_read_tools_source = _read("src/parallax/platform/agent_read_tools.py")
    story_stage_source = _read("src/parallax/domains/news_intel/services/news_story_brief_stage.py")
    item_stage_source = _read("src/parallax/domains/news_intel/services/news_item_brief_stage.py")

    page_item_loader_forbidden = (
        "news_item_agent_briefs",
        "_CURRENT_NEWS_ITEM_BRIEF_CURRENT_BRIEF_SQL",
        "current_brief",
    )
    story_projection_forbidden = (
        "news_item_agent_briefs",
        "_current_brief_for_item",
        "_CURRENT_NEWS_ITEM_BRIEF_STORY_CURRENT_BRIEF_SQL",
        "_CURRENT_NEWS_ITEM_BRIEF_DUPLICATE_CURRENT_BRIEF_SQL",
        "story_current_brief",
        "duplicate_current_brief",
        "fallback_item",
    )
    story_projection_offenders = [
        token
        for token in story_projection_forbidden
        if token in story_projection_source or token in story_current_source
    ]

    assert [token for token in page_item_loader_forbidden if token in page_item_loader_source] == []
    assert "def _current_brief_for_item" not in repository_source
    assert story_projection_offenders == []
    assert "_current_story_agent_briefs_for_story_keys(group_order)" in story_projection_source
    assert "FROM news_story_agent_briefs AS briefs" in story_current_source
    assert "news_item_agent_briefs" not in source_quality_input_source
    assert "JOIN news_story_agent_briefs AS briefs" in source_quality_input_source
    assert "briefs.member_news_item_ids_json ? items.news_item_id" in source_quality_input_source
    assert '"method": "news_story_brief"' in page_projection_source
    assert "news.current_briefs" not in agent_read_tools_source
    assert "news.current_briefs" not in story_stage_source
    assert "news.current_briefs" not in item_stage_source
    assert "news.story_current_briefs" in agent_read_tools_source
    assert "news_story_agent_briefs" in agent_read_tools_source


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


def test_news_item_brief_input_uses_formal_market_scope_without_admission_basis_fallback() -> None:
    path = "src/parallax/domains/news_intel/services/news_item_brief_input.py"
    source = _read(path)
    market_scope_source = _function_source(path, "_market_scope")
    forbidden = {
        'item.get("market_scope_json") or item.get("market_scope")',
        'item.get("market_scope")',
        "_agent_admission_market_scope",
        'basis.get("market_scope")',
    }
    required = {
        '_market_domain_list(item, "market_scope_json")',
        'inferred = [lane.market_domain for lane in entity_lanes if lane.market_domain != "unknown"]',
    }

    assert sorted(token for token in forbidden if token in source) == []
    assert sorted(token for token in required if token not in market_scope_source) == []


def test_news_item_brief_input_rejects_malformed_present_json_fields_without_string_repair() -> None:
    path = "src/parallax/domains/news_intel/services/news_item_brief_input.py"
    source = _read(path)
    market_source = _function_source(path, "_market_domain_list")
    context_source = _function_source(path, "_required_bounded_json_object")
    required = {
        'raise ValueError(f"news_item_brief_{field_name}_required")',
        "raise ValueError(error_code)",
    }
    forbidden = {
        "import json\n",
        "json.loads",
        "except json.JSONDecodeError",
        "def _json_list(",
        "def _json_object(",
        "def _bounded_json_object(",
    }

    assert sorted(token for token in required if token not in "\n".join((market_source, context_source))) == []
    assert sorted(token for token in forbidden if token in source) == []


def test_news_item_brief_input_requires_published_at_without_zero_repair() -> None:
    path = "src/parallax/domains/news_intel/services/news_item_brief_input.py"
    build_source = _function_source(path, "build_news_item_brief_input_packet")
    helper_source = _function_source(path, "_required_item_published_at_ms")
    combined = "\n".join((build_source, helper_source))
    required = {
        "published_at_ms=_required_item_published_at_ms(item)",
        'raise ValueError("news_item_brief_published_at_ms_required")',
    }
    forbidden = {
        'published_at_ms=_int(item.get("published_at_ms"))',
        "def _int(",
        "max(0, int(value or 0))",
        "return 0",
    }

    assert sorted(token for token in required if token not in combined) == []
    assert sorted(token for token in forbidden if token in combined) == []


def test_news_item_brief_input_does_not_restore_context_from_admission_basis() -> None:
    source = "\n".join(
        (
            _read("src/parallax/domains/news_intel/services/news_item_brief_input.py"),
            _function_source(
                "src/parallax/domains/news_intel/runtime/news_item_brief_worker.py",
                "_candidate_with_agent_admission",
            ),
        )
    )
    forbidden = {
        '_context_object(item, "agent_admission_json", "agent_admission")',
        '_context_object(item, "similarity_json", "similarity")',
        '_context_object(item, "material_delta_json", "material_delta")',
        'fallback=agent_admission.get("similarity")',
        'fallback=agent_admission.get("material_delta")',
        'agent_admission.get("similarity")',
        'agent_admission.get("material_delta")',
        'item["similarity_json"] = basis["similarity"]',
        'item["material_delta_json"] = basis["material_delta"]',
        "object_key: str",
        "value = item.get(object_key)",
        'item.get("agent_admission")',
        'item.get("similarity")',
        'item.get("material_delta")',
        "fallback: Any = None",
        "value = fallback",
    }

    assert sorted(token for token in forbidden if token in source) == []


def test_news_item_brief_input_lane_arrays_reject_malformed_present_values() -> None:
    path = "src/parallax/domains/news_intel/services/news_item_brief_input.py"
    entity_source = _function_source(path, "_entity_lane")
    token_source = _function_source(path, "_token_entity_lane")
    fact_source = _function_source(path, "_fact_lane")
    mapping_list_source = _function_source(path, "_optional_lane_mapping_list")
    scalar_list_source = _function_source(path, "_optional_lane_scalar_list")
    required_text_source = _function_source(path, "_required_lane_text")
    combined = "\n".join((entity_source, token_source, fact_source))

    forbidden = {
        '_json_list(row.get("candidate_targets_json"))',
        '_json_list(row.get("affected_targets_json"))',
        '_json_list(row.get("rejection_reasons_json"))',
        "_json_object(value)",
        'row.get("resolution_status") or "unknown"',
    }
    required = {
        '_optional_lane_mapping_list(row, "candidate_targets_json", lane_name="entity")',
        '_optional_lane_mapping_list(row, "candidate_targets_json", lane_name="token")',
        '_optional_lane_mapping_list(row, "affected_targets_json", lane_name="fact")',
        '_optional_lane_scalar_list(row, "rejection_reasons_json", lane_name="fact")',
        '_required_lane_text(row, "resolution_status", lane_name="token")',
        "news_item_brief_{lane_name}_{field_name}_required",
        "if not isinstance(item, Mapping):",
    }

    assert sorted(token for token in forbidden if token in combined) == []
    assert (
        sorted(
            token
            for token in required
            if token not in combined + mapping_list_source + scalar_list_source + required_text_source
        )
        == []
    )


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


def test_news_market_scope_rejects_malformed_present_json_arrays() -> None:
    source = _read("src/parallax/domains/news_intel/services/news_market_scope.py")
    required = {
        '_optional_scope_list(item.get("coverage_tags_json"), "coverage_tags_json")',
        '_optional_scope_list(mention.get("reason_codes"), "reason_codes")',
        '_optional_scope_list(mention.get("reason_codes_json"), "reason_codes_json")',
        '_optional_scope_list(candidate.get("affected_targets"), "affected_targets")',
        '_optional_scope_list(candidate.get("affected_targets_json"), "affected_targets_json")',
        'raise ValueError(f"news_market_scope_{field_name}_required")',
    }
    forbidden = {
        "import json",
        "json.loads",
        "except json.JSONDecodeError",
        "return loaded if isinstance(loaded, list) else []",
        "return dict(loaded) if isinstance(loaded, Mapping) else {}",
    }

    assert sorted(token for token in required if token not in source) == []
    assert sorted(token for token in forbidden if token in source) == []


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


def test_news_page_projection_provider_rating_rejects_malformed_present_provider_signal() -> None:
    source = _function_source(
        "src/parallax/domains/news_intel/services/news_page_projection.py",
        "_provider_rating_payload",
    )
    helper_source = _function_source(
        "src/parallax/domains/news_intel/services/news_page_projection.py",
        "_optional_item_mapping",
    )
    rating_score_source = _function_source(
        "src/parallax/domains/news_intel/services/news_page_projection.py",
        "_optional_rating_score",
    )
    required = {
        '_optional_item_mapping(item, "provider_signal_json"',
        '_optional_rating_score(rating.get("score"), news_item_id=news_item_id)',
        "not isinstance(value, int) or isinstance(value, bool)",
        "news_page_projection_provider_rating_score_required",
        "news_page_projection_item_{field_name}_required",
    }
    forbidden = {
        '_json_object(item.get("provider_signal_json"))',
        'item.get("provider_signal_json") or {}',
        "return int(value)",
        "except (TypeError, ValueError)",
    }

    combined = "\n".join((source, helper_source, rating_score_source))
    compact_combined = "".join(combined.split())
    assert (
        sorted(token for token in required if token not in combined and "".join(token.split()) not in compact_combined)
        == []
    )
    assert sorted(token for token in forbidden if token in combined) == []


def test_news_page_compact_agent_brief_does_not_emit_audit_identity_fields() -> None:
    source = _function_source(
        "src/parallax/domains/news_intel/services/news_page_projection.py",
        "_compact_agent_brief",
    )
    market_impacts_source = _function_source(
        "src/parallax/domains/news_intel/services/news_page_projection.py",
        "_agent_market_impacts",
    )
    optional_mapping_source = _function_source(
        "src/parallax/domains/news_intel/services/news_page_projection.py",
        "_optional_agent_brief_mapping",
    )
    optional_list_source = _function_source(
        "src/parallax/domains/news_intel/services/news_page_projection.py",
        "_optional_agent_brief_list",
    )
    required = {
        '_required_agent_brief_text(agent_brief, "status", news_item_id=news_item_id)',
        '_required_agent_brief_text(agent_brief, "direction", news_item_id=news_item_id)',
        '_required_agent_brief_text(agent_brief, "decision_class", news_item_id=news_item_id)',
        '_required_agent_brief_mapping(agent_brief, "brief_json", news_item_id=news_item_id)',
        '_optional_agent_brief_mapping(brief_json, "bull_view", news_item_id=news_item_id)',
        '_optional_agent_brief_mapping(brief_json, "bear_view", news_item_id=news_item_id)',
        '_optional_agent_brief_list(brief_json, "data_gaps", news_item_id=news_item_id)',
        '_optional_agent_brief_list(brief_json, "market_impacts", news_item_id=news_item_id)',
        "_agent_market_impacts(market_impacts, news_item_id=news_item_id)",
        "news_page_projection_agent_brief_{field_name}_required",
        "news_page_projection_agent_market_impact_required",
        "news_page_projection_agent_market_impact_label_required",
    }
    forbidden = {
        "agent_run_id",
        "artifact_version_hash",
        "input_hash",
        "output_hash",
        "prompt_version",
        "schema_version",
        "validator_version",
        'agent_brief.get("status") or brief_json.get("status") or "pending"',
        'agent_brief.get("direction") or brief_json.get("direction")',
        'agent_brief.get("decision_class") or brief_json.get("decision_class")',
        'return payload or {"status": "pending"}',
        '_json_object(brief_json.get("bull_view"))',
        '_json_object(brief_json.get("bear_view"))',
        'len(_json_list(brief_json.get("data_gaps")))',
        '_agent_market_impacts(brief_json.get("market_impacts"), news_item_id=news_item_id)',
        "_json_list(value)",
        "continue",
    }
    combined = "\n".join((source, market_impacts_source, optional_mapping_source, optional_list_source))
    assert sorted(token for token in required if token not in combined) == []
    offenders = sorted(token for token in forbidden if token in combined)
    assert offenders == []


def test_news_page_projection_lane_arrays_reject_malformed_present_values() -> None:
    projection_path = "src/parallax/domains/news_intel/services/news_page_projection.py"
    token_lane_source = _function_source(projection_path, "_token_lane")
    fact_lane_source = _function_source(projection_path, "_fact_lane")
    helper_source = _function_source(projection_path, "_optional_lane_list")

    forbidden = {
        "_token_lane": (
            '_json_list(row.get("reason_codes_json"))',
            '_json_list(row.get("candidate_targets_json"))',
        ),
        "_fact_lane": (
            '_json_list(row.get("rejection_reasons_json"))',
            '_json_list(row.get("affected_targets_json"))',
        ),
    }
    offenders = [
        f"{source_name} contains {token}"
        for source_name, tokens in forbidden.items()
        for token in tokens
        if token in {"_token_lane": token_lane_source, "_fact_lane": fact_lane_source}[source_name]
    ]

    assert '_optional_lane_list(row, "reason_codes_json", lane_name="token")' in token_lane_source
    assert '_optional_lane_list(row, "candidate_targets_json", lane_name="token")' in token_lane_source
    assert '_optional_lane_list(row, "rejection_reasons_json", lane_name="fact")' in fact_lane_source
    assert '_optional_lane_list(row, "affected_targets_json", lane_name="fact")' in fact_lane_source
    assert "news_page_projection_{lane_name}_lane_{field_name}_required" in helper_source
    assert offenders == []


def test_news_page_external_push_publishable_summary_requires_current_summary_field() -> None:
    source = _function_source(
        "src/parallax/domains/news_intel/services/news_page_projection.py",
        "_agent_publishable_summary",
    )
    required = {
        'value = agent_signal.get("summary_zh")',
        "isinstance(value, str)",
        "bool(value.strip())",
    }
    forbidden = {
        'agent_signal.get("market_read_zh")',
        'agent_signal.get("summary_zh") or',
        "str(",
    }

    assert sorted(token for token in required if token not in source) == []
    assert sorted(token for token in forbidden if token in source) == []


def test_news_public_agent_brief_payload_has_no_item_schema_downgrade_gate() -> None:
    source = "\n".join(
        (
            _function_source(
                "src/parallax/domains/news_intel/repositories/news_repository.py",
                "_public_agent_brief_payload",
            ),
            _function_source(
                "src/parallax/domains/news_intel/repositories/news_repository.py",
                "_required_public_agent_brief_text",
            ),
            _function_source(
                "src/parallax/domains/news_intel/repositories/news_repository.py",
                "_required_public_agent_brief_list",
            ),
            _function_source(
                "src/parallax/domains/news_intel/repositories/news_repository.py",
                "_validate_public_agent_brief_affected_entity",
            ),
        )
    )
    forbidden = {
        "is_current_news_item_brief_contract",
        "has_contract_keys",
        "NEWS_ITEM_BRIEF_SCHEMA_VERSION",
        "prompt_version",
        "schema_version",
        "validator_version",
        'public_payload["status"] = str(public_payload.get("status") or "pending")',
        '_optional_public_agent_brief_mapping(payload, "brief_json")',
        "def _optional_public_agent_brief_mapping",
        '"brief_json"',
        '_json_dict(payload.get("brief_json"))',
        "_json_list(public_payload.get(list_key))",
    }
    required = {
        '_required_public_agent_brief_text(payload, "status")',
        'if public_payload["status"] == "ready":',
        '_required_public_agent_brief_text(public_payload, "direction")',
        '_required_public_agent_brief_text(public_payload, "decision_class")',
        "_validate_public_agent_brief_text_field(public_payload, field_name)",
        "_validate_public_agent_brief_mapping_field(public_payload, field_name)",
        "_validate_public_agent_brief_nonnegative_int_field(",
        "_validate_public_agent_brief_affected_entity(entity)",
        "_required_public_agent_brief_list(public_payload, list_key)",
        "news_public_agent_brief_{field_name}_required",
    }
    offenders = sorted(token for token in forbidden if token in source)
    assert offenders == []
    assert sorted(token for token in required if token not in source) == []


def test_news_item_brief_contract_module_has_no_runtime_row_schema_gate() -> None:
    source = _read("src/parallax/domains/news_intel/types/news_item_brief_contract.py")

    assert "def is_current_news_item_brief_contract" not in source
    assert '"is_current_news_item_brief_contract"' not in source
    assert "str(row.get(" not in source


def test_news_page_projection_wakes_from_story_current_not_item_brief_current() -> None:
    from parallax.app.runtime.worker_manifest import require_worker_manifest
    from parallax.platform.config.settings import WorkersSettings

    manifest_wakes = require_worker_manifest("news_page_projection").wakes_on
    settings_wakes = WorkersSettings().news_page_projection.wakes_on

    assert manifest_wakes == settings_wakes
    assert "news_story_brief_updated" in manifest_wakes
    assert "news_item_brief_updated" not in manifest_wakes


def test_news_item_brief_current_write_does_not_dirty_page_projection() -> None:
    source = _function_source(
        "src/parallax/domains/news_intel/runtime/news_item_brief_worker.py",
        "_upsert_current",
    )
    forbidden = {
        "enqueue_page_reprojection",
        "news_item_brief_updated",
    }
    offenders = sorted(token for token in forbidden if token in source)
    assert offenders == []


def test_news_item_process_enqueues_story_brief_not_item_brief_after_hard_cut() -> None:
    from parallax.app.runtime.worker_manifest import require_worker_manifest
    from parallax.platform.config.settings import WorkersSettings

    source = _read("src/parallax/domains/news_intel/runtime/news_item_process_worker.py")
    item_brief_manifest_wakes = require_worker_manifest("news_item_brief").wakes_on
    item_brief_settings_wakes = WorkersSettings().news_item_brief.wakes_on
    forbidden = {
        "enqueue_item_brief_work",
        "ITEM_BRIEF_INPUT",
        '"brief_input"',
    }
    required = {
        "enqueue_story_brief_work",
        "news_item_agent_brief_priority",
    }

    assert sorted(token for token in forbidden if token in source) == []
    assert sorted(token for token in required if token not in source) == []
    assert item_brief_manifest_wakes == item_brief_settings_wakes == ()


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


def test_news_high_signal_display_title_requires_typed_agent_title_without_string_repair() -> None:
    source = _function_source(
        "src/parallax/domains/notifications/services/notification_rules.py",
        "_news_display_title",
    )

    assert 'agent_brief.get("title_zh") or' not in source
    assert 'display_signal.get("title_zh")' not in source
    assert 'row.get("headline")' not in source
    assert '_news_agent_optional_text(agent_brief, "title_zh")' in source
    assert '_optional_news_signal_text(display_signal, "title_zh", section="display_signal")' in source
    assert '_optional_news_text(row, "headline")' in source
    assert "_compact_text(title, limit=96)" in source


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
            "_required_news_item_detail_list",
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
        '_json_list(row["entities"])',
        '_json_list(row["token_mentions"])',
        '_json_list(row["fact_candidates"])',
        "news_item_agent_briefs",
        "news_item_agent_runs",
        "_detail_agent_brief",
    }
    offenders = sorted(token for token in forbidden if token in source)
    assert offenders == []
    for required in (
        "_required_projected_page_text(",
        "_required_projected_page_mapping(",
        "_required_projected_page_list(",
        "_required_news_item_detail_list(row,",
    ):
        assert required in source
    assert "news_item_detail_projection_required" in helper_sources
    assert "news_item_detail_projection_invalid" in helper_sources
    assert "news_item_detail_evidence_required" in helper_sources
    assert "news_item_detail_evidence_invalid" in helper_sources
    assert '_public_agent_brief_payload(_required_projected_page_mapping(projected, "page_agent_brief"))' in source


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


def test_news_agent_admission_representative_current_state_uses_story_current() -> None:
    load_source = _function_source(
        "src/parallax/domains/news_intel/repositories/news_repository.py",
        "load_agent_admission_contexts",
    )
    similar_story_source = _function_source(
        "src/parallax/domains/news_intel/repositories/news_repository.py",
        "_agent_similar_story_context",
    )
    forbidden = (
        "news_item_agent_briefs AS duplicate_current_brief",
        "news_item_agent_briefs AS story_current_brief",
        "_CURRENT_NEWS_ITEM_BRIEF_DUPLICATE_CURRENT_BRIEF_SQL",
        "_CURRENT_NEWS_ITEM_BRIEF_STORY_CURRENT_BRIEF_SQL",
        'item.get("story_identity_version") or NEWS_STORY_IDENTITY_VERSION',
    )

    assert [token for token in forbidden if token in load_source] == []
    assert "news_story_agent_briefs AS duplicate_story_current_brief" in load_source
    assert "news_story_agent_briefs AS story_current_brief" in load_source
    assert "news_item_agent_briefs" not in similar_story_source
    assert "news_story_agent_briefs AS current_brief" in similar_story_source
    assert '_required_agent_admission_item_text(item, "story_identity_version")' in similar_story_source


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


def test_news_story_similarity_uses_formal_provider_key_arrays_without_scalar_or_json_string_fallback() -> None:
    source = _function_source(
        "src/parallax/domains/news_intel/services/news_story_similarity.py",
        "_provider_article_keys",
    )
    helper_source = _function_source(
        "src/parallax/domains/news_intel/services/news_story_similarity.py",
        "_optional_provider_key_list",
    )
    required = {
        '_optional_provider_key_list(row, "provider_article_keys")',
        '_optional_provider_key_list(row, "provider_article_keys_json")',
        "news_story_similarity_{field_name}_required",
    }
    forbidden = {
        '"provider_article_key"',
        "json.loads",
        "_json_list(",
    }

    combined = "\n".join((source, helper_source))
    assert sorted(token for token in required if token not in combined) == []
    assert sorted(token for token in forbidden if token in combined) == []


def test_news_source_sync_cursor_requires_explicit_scalars_without_zero_fallback() -> None:
    cursor_source = _function_source(
        "src/parallax/domains/news_intel/repositories/news_repository.py",
        "source_sync_cursor",
    )
    helper_source = _function_source(
        "src/parallax/domains/news_intel/repositories/news_repository.py",
        "_required_source_sync_cursor_nonnegative_int",
    )
    required = {
        '_required_source_sync_cursor_nonnegative_int(row, "sync_high_watermark_ms")',
        '_required_source_sync_cursor_nonnegative_int(row, "sync_overlap_ms")',
        "news_source_sync_cursor_{field_name}_required",
    }
    forbidden = {
        'int(row["sync_high_watermark_ms"] or 0)',
        'int(row["sync_overlap_ms"] or 0)',
        'int(row.get("sync_high_watermark_ms") or 0)',
        'int(row.get("sync_overlap_ms") or 0)',
    }

    combined = "\n".join((cursor_source, helper_source))
    assert sorted(token for token in required if token not in combined) == []
    assert sorted(token for token in forbidden if token in combined) == []


def test_news_source_status_payload_rejects_malformed_present_sections() -> None:
    source = _function_source(
        "src/parallax/domains/news_intel/repositories/news_repository.py",
        "_source_status_payload",
    )
    helper_sources = "\n".join(
        _function_source("src/parallax/domains/news_intel/repositories/news_repository.py", function_name)
        for function_name in (
            "_required_source_status_bool",
            "_required_source_status_nonnegative_int",
            "_required_source_status_text",
            "_required_source_status_text_list",
            "_required_latest_fetch_run_nonnegative_int",
            "_required_latest_fetch_run_text",
            "_optional_source_status_mapping",
            "_optional_source_status_present_mapping",
            "_required_latest_quality_mapping",
            "_required_latest_quality_nonnegative_int",
            "_required_latest_quality_payload_text",
            "_required_latest_quality_text",
            "_optional_latest_quality_nonnegative_int",
            "_source_quality_read_payload",
            "_latest_fetch_run_payload",
            "_latest_quality_counts",
            "_provider_health_payload",
            "_provider_capability_tags",
        )
    )
    required = {
        '_required_source_status_text(row, "source_id")',
        '_required_source_status_text(row, "provider_type")',
        '_required_source_status_text(row, "source_domain")',
        '_required_source_status_text(row, "source_name")',
        '_required_source_status_text(row, "source_role")',
        '_required_source_status_text(row, "trust_tier")',
        '_required_source_status_text(row, "source_quality_status")',
        '_required_source_status_bool(row, "enabled")',
        '_required_source_status_bool(row, "managed_by_config")',
        '_required_source_status_nonnegative_int(row, "refresh_interval_seconds")',
        '_required_source_status_nonnegative_int(row, "item_count")',
        '_required_source_status_nonnegative_int(row, "sync_high_watermark_ms")',
        '_required_source_status_nonnegative_int(row, "sync_overlap_ms")',
        '_required_source_status_nonnegative_int(row, "next_fetch_after_ms")',
        '_required_source_status_nonnegative_int(row, "consecutive_failures")',
        '_required_source_status_text_list(row, "coverage_tags_json")',
        '_required_latest_fetch_run_text(row, "status")',
        '_required_latest_fetch_run_nonnegative_int(row, "fetched_count")',
        '_required_latest_fetch_run_nonnegative_int(row, "inserted_count")',
        '_required_latest_fetch_run_nonnegative_int(row, "updated_count")',
        '_required_latest_fetch_run_nonnegative_int(row, "duplicate_count")',
        '_optional_source_status_present_mapping(row, "latest_quality_json")',
        '_optional_source_status_present_mapping(row, "latest_fetch_run_json")',
        '_optional_source_status_mapping(row, "sync_diagnostics_json")',
        '_optional_source_status_mapping(row, "dedup_diagnostics_json")',
        "news_source_status_{field_name}_required",
        '_required_latest_quality_payload_text(row, "row_id")',
        '_required_latest_quality_payload_text(row, "source_id")',
        '_required_latest_quality_payload_text(row, "window")',
        '_required_latest_quality_payload_text(row, "projection_version")',
        '_required_latest_quality_nonnegative_int(row, "computed_at_ms")',
        '_required_latest_quality_nonnegative_int(row, "items_fetched")',
        '_required_latest_quality_nonnegative_int(row, "items_inserted")',
        '_optional_latest_quality_nonnegative_int(row, "median_lag_ms")',
        '_required_latest_quality_mapping(row, "diagnostics_json")',
        '_required_latest_quality_text(diagnostics, "status")',
        "news_source_status_latest_quality_{field_name}_required",
        "news_source_status_latest_quality_diagnostics_{field_name}_required",
        "enabled=enabled",
        "consecutive_failures=consecutive_failures",
        "source_quality_status=source_quality_status",
        "_provider_capability_tags(",
        "provider_type=provider_type",
        "source_role=source_role",
        "trust_tier=trust_tier",
    }
    source_forbidden = {
        '"source_id": str(row["source_id"])',
        '"provider_type": str(row.get("provider_type") or "")',
        '"source_domain": str(row.get("source_domain") or "")',
        '"source_name": str(row.get("source_name") or "")',
        '"source_role": str(row.get("source_role") or "")',
        '"trust_tier": str(row.get("trust_tier") or "")',
        '"source_quality_status": str(row.get("source_quality_status") or "unknown")',
        '"enabled": bool(row.get("enabled"))',
        '"managed_by_config": bool(row.get("managed_by_config"))',
        '"refresh_interval_seconds": int(row.get("refresh_interval_seconds") or 0)',
        '"item_count": int(row.get("item_count") or 0)',
        '"sync_high_watermark_ms": int(row.get("sync_high_watermark_ms") or 0)',
        '"sync_overlap_ms": int(row.get("sync_overlap_ms") or 0)',
        '"next_fetch_after_ms": int(row.get("next_fetch_after_ms") or 0)',
        '"consecutive_failures": int(row.get("consecutive_failures") or 0)',
        "quality_payload = _source_quality_read_payload(latest_quality) if latest_quality else None",
    }
    latest_fetch_run_forbidden = {
        "if not row:",
        '"status": str(row.get("status") or "unknown")',
        '"fetched_count": int(row.get("fetched_count") or 0)',
        '"inserted_count": int(row.get("inserted_count") or 0)',
        '"updated_count": int(row.get("updated_count") or 0)',
        '"duplicate_count": int(row.get("duplicate_count") or 0)',
    }
    provider_health_forbidden = {
        'consecutive_failures = int(row.get("consecutive_failures") or 0)',
        'if not bool(row.get("enabled"))',
        'quality_status = str(row.get("source_quality_status") or "unknown")',
        'quality_status = str(diagnostics.get("status") or quality_status)',
    }
    provider_capability_forbidden = {
        'provider_type = str(row.get("provider_type") or "").strip().lower()',
        'source_role = str(row.get("source_role") or "").strip().lower()',
        'trust_tier = str(row.get("trust_tier") or "").strip().lower()',
    }
    forbidden = {
        '_json_list(row.get("coverage_tags_json"))',
        'row.get("coverage_tags_json") or []',
        '_json_dict(row.get("latest_quality_json"))',
        '_json_dict(row.get("latest_fetch_run_json"))',
        '_json_dict(row.get("sync_diagnostics_json"))',
        '_json_dict(row.get("dedup_diagnostics_json"))',
        '_json_dict(row.get("diagnostics_json"))',
        '_json_dict(latest_quality.get("diagnostics_json"))',
        '_json_dict(quality_payload.get("diagnostics_json"))',
        '"row_id": str(row["row_id"])',
        '"source_id": str(row["source_id"])',
        '"window": str(row["window"])',
        '"computed_at_ms": int(row["computed_at_ms"])',
        '"items_fetched": int(row.get("items_fetched") or 0)',
        '"items_inserted": int(row.get("items_inserted") or 0)',
        '"median_lag_ms": int(row["median_lag_ms"]) if row.get("median_lag_ms") is not None else None',
        '"projection_version": str(row["projection_version"])',
    }

    combined = "\n".join((source, helper_sources))
    latest_fetch_run_source = _function_source(
        "src/parallax/domains/news_intel/repositories/news_repository.py",
        "_latest_fetch_run_payload",
    )
    provider_health_source = _function_source(
        "src/parallax/domains/news_intel/repositories/news_repository.py",
        "_provider_health_payload",
    )
    provider_capability_source = _function_source(
        "src/parallax/domains/news_intel/repositories/news_repository.py",
        "_provider_capability_tags",
    )
    assert sorted(token for token in required if token not in combined) == []
    assert sorted(token for token in source_forbidden if token in source) == []
    assert sorted(token for token in latest_fetch_run_forbidden if token in latest_fetch_run_source) == []
    assert sorted(token for token in provider_health_forbidden if token in provider_health_source) == []
    assert sorted(token for token in provider_capability_forbidden if token in provider_capability_source) == []
    assert sorted(token for token in forbidden if token in combined) == []


def test_news_source_quality_write_payload_rejects_malformed_required_sections() -> None:
    path = "src/parallax/domains/news_intel/repositories/news_repository.py"
    source = _function_source(path, "_source_quality_payload")
    helper_sources = "\n".join(
        _function_source(path, function_name)
        for function_name in (
            "_required_source_quality_payload_text",
            "_required_source_quality_payload_nonnegative_int",
            "_optional_source_quality_payload_nonnegative_int",
            "_required_source_quality_payload_mapping",
            "_required_source_quality_payload_diagnostics_text",
        )
    )
    replace_source = _function_source(path, "replace_source_quality_rows")
    required = {
        '_required_source_quality_payload_text(row, "row_id")',
        '_required_source_quality_payload_text(row, "source_id")',
        '_required_source_quality_payload_text(row, "window")',
        '_required_source_quality_payload_text(row, "projection_version")',
        '_required_source_quality_payload_nonnegative_int(row, "computed_at_ms")',
        '_required_source_quality_payload_nonnegative_int(row, "items_fetched")',
        '_required_source_quality_payload_nonnegative_int(row, "items_inserted")',
        '_optional_source_quality_payload_nonnegative_int(row, "median_lag_ms")',
        '_required_source_quality_payload_mapping(row, "diagnostics_json")',
        '_required_source_quality_payload_diagnostics_text(diagnostics_json, "status")',
        "news_source_quality_payload_{field_name}_required",
        "news_source_quality_payload_diagnostics_{field_name}_required",
    }
    forbidden = {
        '"row_id": str(row["row_id"])',
        '"source_id": str(row["source_id"])',
        '"window": str(row["window"])',
        '"computed_at_ms": int(row["computed_at_ms"])',
        '"items_fetched": int(row.get("items_fetched") or 0)',
        '"items_inserted": int(row.get("items_inserted") or 0)',
        '"median_lag_ms": int(row["median_lag_ms"]) if row.get("median_lag_ms") is not None else None',
        '"diagnostics_json": _json(row.get("diagnostics_json") or {})',
        '"projection_version": str(row["projection_version"])',
    }
    replace_forbidden = {
        '_json_dict(row.get("diagnostics_json")).get("status")',
        'str(status or "unknown")',
    }
    combined = "\n".join((source, helper_sources))

    assert sorted(token for token in required if token not in combined) == []
    assert sorted(token for token in forbidden if token in source) == []
    assert sorted(token for token in replace_forbidden if token in replace_source) == []


def test_source_quality_projection_counts_and_optional_timings_have_no_int_repair() -> None:
    path = "src/parallax/domains/news_intel/services/source_quality_projection.py"
    count_source = _function_source(path, "_count")
    optional_int_source = _function_source(path, "_optional_nonnegative_int")
    metrics_source = _function_source(path, "_metrics_from_input")
    row_source = _function_source(path, "build_source_quality_row")
    freshness_source = _function_source(path, "_normalized_freshness")
    combined = "\n".join((count_source, optional_int_source, metrics_source, row_source, freshness_source))
    required = {
        '_optional_nonnegative_int(row, "latest_item_published_at_ms")',
        '_optional_nonnegative_int(counts or {}, "median_lag_ms")',
        "news_source_quality_projection_count_{key}_required",
        "news_source_quality_projection_{key}_required",
        "not isinstance(value, int) or isinstance(value, bool) or value < 0",
        "age_ms = max(0, computed_at_ms - latest_item_published_at_ms)",
    }
    forbidden = {
        "return max(0, int(value))",
        "return int(value)",
        "int(computed_at_ms) - int(latest_item_published_at_ms)",
        "int(window_ms)",
    }

    assert sorted(token for token in required if token not in combined) == []
    assert sorted(token for token in forbidden if token in combined) == []


def test_news_source_hygiene_uses_projected_provider_health_without_quality_status_fallback() -> None:
    capabilities_source = _function_source("src/parallax/app/surfaces/api/routes_news.py", "_provider_capabilities")
    hygiene_source = _function_source("src/parallax/app/surfaces/api/routes_news.py", "_source_hygiene")
    helper_sources = "\n".join(
        _function_source("src/parallax/app/surfaces/api/routes_news.py", function_name)
        for function_name in ("_required_source_mapping", "_required_source_text", "_required_source_text_list")
    )
    required = {
        '_required_source_text(source, "provider_type")',
        '_required_source_text_list(source, "coverage_tags")',
        '_required_source_mapping(source, "provider_health")',
        '_required_source_text(health, "status", label="provider_health_status")',
        "news_source_status_{field_name}_required",
        "news_source_status_{error_label}_required",
    }
    forbidden = {
        'str(source.get("provider_type") or "")',
        'if source.get("provider_type")',
        'not source.get("coverage_tags")',
        'health = source.get("provider_health") if isinstance(source.get("provider_health"), dict) else {}',
        'health.get("status") or source.get("source_quality_status") or ""',
        'str(source.get("source_id") or "")',
        "if not source_id:\n            continue",
    }
    combined = "\n".join((capabilities_source, hygiene_source, helper_sources))

    assert sorted(token for token in required if token not in combined) == []
    assert sorted(token for token in forbidden if token in combined) == []


def test_news_page_projection_source_payload_rejects_malformed_source_fields() -> None:
    source = _function_source(
        "src/parallax/domains/news_intel/services/news_page_projection.py",
        "_source_payload",
    )
    helper_source = _function_source(
        "src/parallax/domains/news_intel/services/news_page_projection.py",
        "_optional_item_list",
    )
    required = {
        '_optional_item_list(item, "coverage_tags_json"',
        '_required_item_text(item, "source_quality_status"',
        "news_page_projection_item_{field_name}_required",
    }
    forbidden = {
        '_json_list(item.get("coverage_tags_json"))',
        'item.get("coverage_tags_json") or []',
        'item.get("source_quality_status") or "unknown"',
    }

    combined = "\n".join((source, helper_source))
    compact_combined = "".join(combined.split())
    assert (
        sorted(token for token in required if token not in combined and "".join(token.split()) not in compact_combined)
        == []
    )
    assert sorted(token for token in forbidden if token in source) == []


def test_news_agent_input_loaders_require_explicit_arrays_without_json_list_defaults() -> None:
    repository_path = "src/parallax/domains/news_intel/repositories/news_repository.py"
    brief_target_source = _function_source(repository_path, "load_items_for_brief_targets")
    admission_context_source = _function_source(repository_path, "load_agent_admission_contexts")
    helper_sources = "\n".join(
        _function_source(repository_path, function_name)
        for function_name in (
            "_required_news_item_brief_target_list",
            "_required_agent_admission_context_list",
            "_required_repository_json_list",
        )
    )
    forbidden = {
        '_json_list(row["entities"])',
        '_json_list(row["token_mentions"])',
        '_json_list(row["fact_candidates"])',
        '_json_list(row["exact_duplicate_candidates"])',
        '_json_list(row["story_candidates"])',
    }
    combined = "\n".join((brief_target_source, admission_context_source))
    required = {
        '_required_news_item_brief_target_list(row, "token_mentions")',
        '_required_news_item_brief_target_list(row, "fact_candidates")',
        '_required_news_item_brief_target_list(row, "entities")',
        "news_item_brief_target_evidence",
        "news_agent_admission_context",
        'raise ValueError(f"{error_prefix}_required:{field_name}")',
        'raise ValueError(f"{error_prefix}_invalid:{field_name}")',
    }

    assert sorted(token for token in forbidden if token in combined) == []
    assert sorted(token for token in required if token not in combined and token not in helper_sources) == []
    assert admission_context_source.count("_required_agent_admission_context_list(") == 5
    for field_name in (
        "entities",
        "token_mentions",
        "fact_candidates",
        "exact_duplicate_candidates",
        "story_candidates",
    ):
        assert f'"{field_name}"' in admission_context_source


def test_news_item_brief_worker_requires_repository_admission_contexts() -> None:
    load_source = _function_source(
        "src/parallax/domains/news_intel/runtime/news_item_brief_worker.py",
        "_load_candidates",
    )
    admission_source = _function_source(
        "src/parallax/domains/news_intel/runtime/news_item_brief_worker.py",
        "_admission_from_candidate",
    )
    compact_load_source = "".join(load_source.split())

    assert 'getattr(repos.news, "load_agent_admission_contexts"' not in load_source
    assert "return candidates" not in load_source
    assert 'or _list_of_dicts(candidate.get("entities"))' not in load_source
    assert 'or _list_of_dicts(candidate.get("token_mentions"))' not in load_source
    assert 'or _list_of_dicts(candidate.get("fact_candidates"))' not in load_source
    assert 'context.get("current_brief") or candidate.get("current_brief")' not in load_source
    assert '_required_admission_context_list(context,"entities",reason="load_candidate")' in compact_load_source
    assert '_required_admission_context_list(context,"token_mentions",reason="load_candidate")' in compact_load_source
    assert '"fact_candidates":_required_admission_context_list(' in compact_load_source
    assert 'context,"fact_candidates",reason="load_candidate"' in compact_load_source
    assert "_required_admission_context_current" not in load_source
    assert '"current_brief":_required_admission_context_current' not in compact_load_source
    assert '"exact_duplicate_candidates": []' not in admission_source
    assert '"story_candidates": []' not in admission_source


def test_news_item_brief_worker_rejects_malformed_candidate_arrays_without_empty_defaults() -> None:
    path = "src/parallax/domains/news_intel/runtime/news_item_brief_worker.py"
    source = _read(path)
    packet_source = _function_source(path, "_packet_from_candidate")
    admission_source = _function_source(path, "_admission_from_candidate")
    helper_source = _function_source(path, "_candidate_list_of_dicts")
    compact_sources = "".join("\n".join((packet_source, admission_source)).split())
    call_required = {
        '_candidate_list_of_dicts(candidate.get("entities"), field="entities")',
        '_candidate_list_of_dicts(candidate.get("token_mentions"), field="token_mentions")',
        '_candidate_list_of_dicts(candidate.get("fact_candidates"), field="fact_candidates")',
    }
    helper_required = {
        'raise RuntimeError(f"news_item_brief_candidate_{field}_array_required")',
        'raise RuntimeError(f"news_item_brief_candidate_{field}_row_object_required")',
    }
    forbidden = {
        "def _list_of_dicts(",
        "return []",
    }

    assert "def _list_of_dicts(" not in source
    assert sorted(token for token in call_required if token.replace(" ", "") not in compact_sources) == []
    assert sorted(token for token in helper_required if token not in helper_source) == []
    assert sorted(token for token in forbidden if token in helper_source) == []


def test_news_brief_target_loaders_require_source_updated_at_without_zero_fallback() -> None:
    path = "src/parallax/domains/news_intel/repositories/news_repository.py"
    item_target_source = _function_source(path, "load_items_for_brief_targets")
    story_target_source = _function_source(path, "load_story_brief_targets")
    helper_source = _function_source(path, "_required_brief_target_source_updated_at_ms")
    combined = "\n".join((item_target_source, story_target_source, helper_source))
    required = {
        '"source_updated_at_ms": _required_brief_target_source_updated_at_ms(row)',
        'int(grouped[story_key]["source_updated_at_ms"])',
        "news_brief_target_source_updated_at_ms_required",
    }
    forbidden = {
        'int(row["source_updated_at_ms"] or 0)',
        'int(row.get("source_updated_at_ms") or 0)',
    }

    assert sorted(token for token in required if token not in combined) == []
    assert sorted(token for token in forbidden if token in combined) == []


def test_news_item_brief_reused_run_identity_requires_run_id_without_empty_fallback() -> None:
    path = "src/parallax/domains/news_intel/runtime/news_item_brief_worker.py"
    source = _read(path)
    completed_validation_source = _function_source(path, "_completed_run_validation")
    fresh_completed_source = _function_source(path, "_fresh_completed_run")
    invalid_completed_source = _function_source(path, "_invalid_completed_run")
    invalid_completed_audit_source = _function_source(path, "_invalid_completed_run_audit")
    restore_completed_source = _function_source(path, "_restore_current_from_completed_run")
    backpressure_error_source = _function_source(path, "_backpressure_outcome_for_error")
    fresh_failed_source = _function_source(path, "_fresh_failed_run")
    failed_outcome_source = _function_source(path, "_failed_run_outcome")
    current_source = _function_source(path, "_current_brief_is_fresh")
    current_text_source = _function_source(path, "_required_current_text")
    current_status_source = _function_source(path, "_required_current_status")
    candidate_index_source = _function_source(path, "_candidates_by_news_item_id")
    candidate_item_source = _function_source(path, "_required_candidate_item")
    run_status_source = _function_source(path, "_required_run_status")
    run_text_source = _function_source(path, "_required_run_text")
    validation_payload_source = _function_source(path, "_required_validation_payload")
    run_execution_started_source = _function_source(path, "_required_run_execution_started")
    run_finished_at_source = _function_source(path, "_required_run_finished_at_ms")
    failed_error_class_source = _function_source(path, "_required_failed_run_error_class")
    failed_error_source = _function_source(path, "_required_failed_run_error")
    completed_sources = "\n".join((completed_validation_source, fresh_completed_source, invalid_completed_source))
    failed_sources = "\n".join((fresh_failed_source, failed_outcome_source))
    forbidden = {
        'run_id=str(run.get("run_id") or "")',
        'failed_current_run_id=str(run.get("run_id") or "")',
        'source_run_id = str(source_run.get("run_id") or "")',
        'if not str(run.get("run_id") or ""):\n        return None',
        'completed_run.get("outcome") or "ready"',
        'audit.get("latency_ms") or 0',
        'audit.get("provider") or self.provider.provider',
        'audit.get("model") or agent_config.model',
        'audit.get("backend") or "litellm_sdk"',
        'audit.get("workflow_name") or agent_config.workflow_name',
        'audit.get("agent_name") or agent_config.agent_name',
        'audit.get("lane") or agent_config.lane',
        'audit.get("prompt_version") or agent_config.prompt_version',
        'audit.get("schema_version") or agent_config.schema_version',
        'audit.get("input_hash") or packet.input_hash',
        '_audit_dict(result.get("agent_run_audit") if isinstance(result, Mapping) else None) or request_audit',
        "if value is None:\n        return {}",
        '_dict(audit.get("trace_metadata"))',
        '_dict(audit.get("usage"))',
        'run.get("finished_at_ms") or now_ms',
        'source_run.get("provider") or "deterministic"',
        'source_run.get("model") or agent_config.model',
        "validation.payload or {}",
        'getattr(error, "error_class", None)',
        'candidate.get("item", {}).get("news_item_id") or ""',
        'context.get("item", {}).get("news_item_id") or ""',
        '_dict(candidate.get("item") or candidate)',
        '_dict(result.get("item") or result)',
    }
    completed_forbidden = {'str(run.get("outcome") or "")'}
    failed_forbidden = {
        'str(run.get("status") or "")',
        'str(run.get("outcome") or "")',
        'bool(run.get("execution_started"))',
        'str(run.get("input_hash") or "")',
        'str(run.get("artifact_version_hash") or "")',
        'str(run.get("prompt_version") or "")',
        'str(run.get("schema_version") or "")',
        'str(run.get("validator_version") or "")',
        'run.get("error_class") or "agent_brief_failed"',
        'run.get("error") or error_class',
    }
    current_forbidden = {
        'current.get("status") or ""',
        'current.get("input_hash") or ""',
        'current.get("artifact_version_hash") or ""',
        'current.get("prompt_version") or ""',
        'current.get("schema_version") or ""',
        'current.get("validator_version") or ""',
    }

    assert sorted(token for token in forbidden if token in source) == []
    assert sorted(token for token in completed_forbidden if token in completed_sources) == []
    assert sorted(token for token in failed_forbidden if token in failed_sources) == []
    assert sorted(token for token in current_forbidden if token in current_source) == []
    assert "news_item_brief_run_id_required" in source
    assert "news_item_brief_run_outcome_required" in source
    assert "news_item_brief_validation_payload_required" in validation_payload_source
    assert "news_item_brief_candidate_item_required:{reason}" in candidate_item_source
    assert "news_item_brief_agent_backpressure_error_contract_required" in backpressure_error_source
    assert "news_item_brief_run_status_required:latest_run" in run_status_source
    assert "news_item_brief_run_{field}_required:{reason}" in run_text_source
    assert "news_item_brief_run_execution_started_required:{reason}" in run_execution_started_source
    assert "news_item_brief_run_finished_at_ms_required:{reason}" in run_finished_at_source
    assert "not isinstance(value, int)" in run_finished_at_source
    assert "int(value)" not in run_finished_at_source
    assert "news_item_brief_run_error_class_required:failed_run" in failed_error_class_source
    assert "news_item_brief_run_error_required:failed_run" in failed_error_source
    assert "news_item_brief_audit_latency_ms_required" in source
    assert "news_item_brief_audit_{field_name}_required" in source
    assert "news_item_brief_current_{field}_required" in current_text_source
    assert "news_item_brief_current_status_required" in current_status_source
    assert "_required_run_id(run, reason=" in source
    assert "_backpressure_outcome_for_error(error)" in source
    assert "_required_validation_payload(validation)" in source
    assert '_candidates_by_news_item_id(candidates, reason="load_candidate")' in source
    assert '_candidates_by_news_item_id(contexts, reason="admission_context")' in source
    assert '_required_candidate_item(candidate, reason="packet")' in source
    assert '_required_candidate_item(candidate, reason="admission")' in source
    assert '_required_candidate_item(result, reason="agent_admission")' in source
    assert "_required_candidate_news_item_id(item, reason=reason)" in candidate_index_source
    assert "_required_run_status(run)" in fresh_failed_source
    assert '_required_run_outcome(run, reason="failed_run", allowed={"failed"})' in fresh_failed_source
    assert '_required_run_text(run, "input_hash", reason="failed_run")' in fresh_failed_source
    assert '_required_run_text(run, "artifact_version_hash", reason="failed_run")' in fresh_failed_source
    assert '_required_run_text(run, "validator_version", reason="failed_run")' in fresh_failed_source
    assert '_required_run_execution_started(run, reason="failed_run")' in fresh_failed_source
    assert '_required_run_finished_at_ms(run, reason="completed_run")' in restore_completed_source
    assert '_required_run_text(source_run, "provider", reason="invalid_completed_source_run")' in (
        invalid_completed_audit_source
    )
    assert '_required_run_text(source_run, "model", reason="invalid_completed_source_run")' in (
        invalid_completed_audit_source
    )
    assert "_required_failed_run_error_class(run)" in failed_outcome_source
    assert "_required_failed_run_error(run)" in failed_outcome_source
    assert "_required_current_status(current)" in current_source
    assert '_required_current_text(current, "input_hash")' in current_source
    assert '_required_current_text(current, "artifact_version_hash")' in current_source
    assert '_required_current_text(current, "validator_version")' in current_source
    assert "_required_audit_latency_ms(audit)" in source
    assert 'audit = _audit_dict(result.get("agent_run_audit") if isinstance(result, Mapping) else None)' in source
    assert '_required_audit_text(audit, "provider")' in source
    assert '_required_audit_text(audit, "backend")' in source
    assert '_required_audit_text(audit, "input_hash")' in source
    assert '_required_audit_mapping(audit, "trace_metadata")' in source
    assert '_required_audit_mapping(audit, "usage")' in source
    assert '_required_run_outcome(run, reason="completed_run", allowed={"ready", "insufficient"})' in (
        completed_validation_source
    )
    assert 'status = str(completed_run["outcome"])' in source
    assert 'source_run_id = _required_run_id(run, reason="invalid_completed_source_run")' in source
    assert '"source_run_id": source_run_id' in source


def test_news_item_brief_worker_requires_claim_contract_without_target_id_fallback() -> None:
    path = "src/parallax/domains/news_intel/runtime/news_item_brief_worker.py"
    source = _read(path)
    claim_target_source = _function_source(path, "_required_item_brief_target_news_item_id")
    claim_text_source = _function_source(path, "_require_claim_text")
    claim_window_source = _function_source(path, "_require_claim_empty_window")
    combined = "\n".join((claim_target_source, claim_text_source, claim_window_source))

    required = {
        "_required_item_brief_target_news_item_id(target)",
        '_require_claim_text(target, field="projection_name", expected=ITEM_BRIEF_INPUT)',
        '_require_claim_text(target, field="target_kind", expected="news_item")',
        "_require_claim_empty_window(target)",
        'return _require_claim_text(target, field="target_id")',
        'f"news_item_brief_claim_{field}_required"',
        "news_item_brief_claim_window_empty_required",
    }
    forbidden = {
        'target.get("target_id") or ""',
        'str(target.get("target_id")',
    }

    assert sorted(token for token in required if token not in source + combined) == []
    assert sorted(token for token in forbidden if token in source) == []


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
        'item.get("material_delta_json")',
        'admission_payload.get("status") or item.get("agent_admission_status")',
        'item.get("market_scope")',
        'payload.get("scope") or payload.get("market_scope")',
        'payload.get("primary") or payload.get("market_scope_primary")',
    }
    assert sorted(token for token in forbidden if token in admission_source) == []
    assert sorted(token for token in forbidden if token in policy_source) == []
    assert sorted(token for token in forbidden if token in cli_parser_source) == []
    assert sorted(token for token in forbidden if token in brief_worker_source) == []


def test_news_item_agent_policy_rejects_malformed_present_policy_fields() -> None:
    source = _read("src/parallax/domains/news_intel/services/news_item_agent_policy.py")
    required = {
        '_optional_policy_mapping(item.get("agent_admission_json"), "agent_admission_json")',
        '_optional_policy_mapping(admission_payload.get("basis"), "basis")',
        '_optional_policy_mapping(value, "material_delta")',
        '_optional_policy_list(payload.get("changed_fields"), "material_delta_changed_fields")',
        '_optional_policy_list(payload.get("reasons"), "material_delta_reasons")',
        '_scope_names(item.get("market_scope_json"), field_name="market_scope_json")',
        'raise ValueError(f"news_item_agent_policy_{field_name}_required")',
    }
    forbidden = {
        "import json",
        "json.loads",
        "return dict(parsed) if isinstance(parsed, Mapping) else {}",
        "return parsed if isinstance(parsed, list) else []",
    }

    assert sorted(token for token in required if token not in source) == []
    assert sorted(token for token in forbidden if token in source) == []


def test_news_item_agent_admission_rejects_malformed_present_json_fields() -> None:
    source = _read("src/parallax/domains/news_intel/services/news_item_agent_admission.py")
    required = {
        '_optional_admission_mapping(item.get("content_classification_json"), "content_classification_json")',
        '_optional_admission_mapping(item.get("source_policy_json"), "source_policy_json")',
        '_optional_admission_mapping(item.get("provider_signal_json"), "provider_signal_json")',
        "_optional_admission_mapping_list(",
        '"representative_entities"',
        '"representative_fact_candidates"',
        'raise ValueError(f"news_item_agent_admission_{field_name}_required")',
    }
    forbidden = {
        "import json",
        "json.loads",
        "except json.JSONDecodeError",
        "return dict(parsed) if isinstance(parsed, Mapping) else {}",
        "return parsed if isinstance(parsed, list) else []",
    }

    assert sorted(token for token in required if token not in source) == []
    assert sorted(token for token in forbidden if token in source) == []


def test_news_item_agent_admission_provider_rating_score_has_no_int_repair() -> None:
    path = "src/parallax/domains/news_intel/services/news_item_agent_admission.py"
    provider_rating_source = _function_source(path, "_provider_rating")
    provider_rating_gate_source = _function_source(path, "_provider_rating_gate")
    provider_score_source = _function_source(path, "_provider_rating_score")
    combined = "\n".join((provider_rating_source, provider_rating_gate_source, provider_score_source))
    required = {
        '_provider_rating_score(signal.get("score"))',
        "score < _PROVIDER_RATING_AGENT_MIN_SCORE",
        "not isinstance(value, int) or isinstance(value, bool) or value < 0",
        "news_item_agent_admission_provider_rating_score_required",
    }
    forbidden = {
        '_optional_int(signal.get("score"))',
        "int(score)",
        "return int(value)",
        "except (TypeError, ValueError)",
    }

    assert sorted(token for token in required if token not in combined) == []
    assert sorted(token for token in forbidden if token in combined) == []


def test_news_item_agent_admission_context_rejects_malformed_present_repository_sections() -> None:
    source = _read("src/parallax/domains/news_intel/types/news_item_agent_admission.py")
    required = {
        '_optional_context_mapping_list(context, "exact_duplicate_candidates")',
        '_optional_context_mapping_list(context, "story_candidates")',
        '_optional_context_mapping(context, "material_delta")',
        'raise ValueError(f"news_item_agent_admission_context_{field_name}_required")',
    }
    forbidden = {
        '_list_of_mappings(context.get("exact_duplicate_candidates"))',
        '_list_of_mappings(context.get("story_candidates"))',
        '_optional_mapping(context.get("material_delta")) or {}',
        "return [item for item in value if isinstance(item, Mapping)]",
        "def _list_of_mappings(",
        "def _optional_mapping(",
    }

    assert sorted(token for token in required if token not in source) == []
    assert sorted(token for token in forbidden if token in source) == []


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
                "_required_page_text",
            ),
            _function_source(
                "src/parallax/domains/news_intel/repositories/news_repository.py",
                "_required_page_string",
            ),
            _function_source(
                "src/parallax/domains/news_intel/repositories/news_repository.py",
                "_required_page_mapping",
            ),
            _function_source(
                "src/parallax/domains/news_intel/repositories/news_repository.py",
                "_required_page_list",
            ),
            _function_source(
                "src/parallax/domains/news_intel/repositories/news_repository.py",
                "_required_page_positive_int",
            ),
            _function_source(
                "src/parallax/domains/news_intel/repositories/news_repository.py",
                "_optional_page_positive_int",
            ),
            _function_source(
                "src/parallax/domains/news_intel/repositories/news_repository.py",
                "_agent_admission_mapping_payload",
            ),
            _function_source(
                "src/parallax/domains/news_intel/repositories/news_repository.py",
                "_required_page_nested_text",
            ),
            _function_source(
                "src/parallax/domains/news_intel/repositories/news_repository.py",
                "_required_page_nested_mapping",
            ),
            _function_source(
                "src/parallax/domains/news_intel/repositories/news_repository.py",
                "_require_page_agent_admission_match",
            ),
        )
    )
    required = {
        "_required_page_text(payload,",
        '_required_page_string(payload, "headline")',
        '_required_page_string(payload, "canonical_url")',
        '_required_page_string(payload, "summary")',
        '_required_page_string(payload, "source_domain")',
        '_required_page_positive_int(payload, "latest_at_ms")',
        '_required_page_positive_int(payload, "computed_at_ms")',
        '_optional_page_positive_int(payload, "agent_brief_computed_at_ms")',
        '_required_page_text(payload, "content_class")',
        '_required_page_text(payload, "agent_status")',
        "_required_page_list(payload,",
        "_required_page_mapping(payload,",
        "_required_page_nested_text(",
        '_required_page_nested_text(agent_brief, "agent_brief", "status")',
        '_required_page_nested_text(agent_brief, "agent_brief", "direction")',
        '_required_page_nested_text(agent_brief, "agent_brief", "decision_class")',
        "_required_page_nested_mapping(",
        "_require_page_agent_admission_match(",
        "news_page_row_payload_required",
        "news_page_row_payload_invalid",
        "news_page_row_payload_invalid:agent_status_mismatch",
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
        'payload["headline"] = str(payload.get("headline") or "")',
        'payload["canonical_url"] = str(payload.get("canonical_url") or "")',
        'payload["summary"] = str(payload.get("summary") or "")',
        'payload["search_text"] = str(payload.get("search_text") or "")',
        'str(payload.get("content_class") or "low_signal")',
        'str(payload.get("agent_status") or "pending")',
        'payload.get("market_scope") or {}',
        'payload.get("representative_news_item_id") or payload.get("news_item_id")',
        'payload.get("story_key") or ""',
        'payload["latest_at_ms"] = int(payload["latest_at_ms"])',
        'payload["computed_at_ms"] = int(payload["computed_at_ms"])',
        'int(payload["agent_brief_computed_at_ms"])',
        'payload.get("agent_admission_status") or agent_admission["status"]',
        'payload.get("agent_admission_reason") or agent_admission["reason"]',
        'payload.get("status") or "needs_review"',
        'payload.get("reason") or ""',
        'payload.get("version") or NEWS_ITEM_AGENT_ADMISSION_VERSION',
        'str(payload.get("representative_news_item_id") or "")',
        '"basis": dict(basis) if isinstance(basis, Mapping) else {},',
        'payload.get("agent_representative_news_item_id") or agent_admission.get("representative_news_item_id")',
    }
    assert sorted(token for token in required if token not in source) == []
    assert sorted(token for token in forbidden if token in source) == []


def test_news_repository_has_no_retired_agent_admission_public_payload_repair() -> None:
    source = _read("src/parallax/domains/news_intel/repositories/news_repository.py")
    forbidden = {
        "def _agent_admission_public_payload",
        'row.get("agent_admission_status") or payload.get("status") or "needs_review"',
        'row.get("agent_admission_reason") or payload.get("reason") or ""',
        "or NEWS_ITEM_AGENT_ADMISSION_VERSION",
        'row.get("agent_representative_news_item_id")\n            or payload.get("representative_news_item_id")',
    }
    offenders = sorted(token for token in forbidden if token in source)
    assert offenders == []


def test_news_page_row_summary_fields_require_explicit_payload_without_defaults() -> None:
    source = "\n".join(
        (
            _function_source(
                "src/parallax/domains/news_intel/repositories/news_repository.py",
                "_apply_page_row_summary",
            ),
            _function_source(
                "src/parallax/domains/news_intel/repositories/news_repository.py",
                "_required_page_nonnegative_int",
            ),
        )
    )
    required = {
        '_required_page_text(payload, "canonical_item_key")',
        '_required_page_nonnegative_int(payload, "duplicate_count")',
        '_required_page_list(payload, "source_ids_json")',
        '_required_page_list(payload, "source_domains_json")',
        '_required_page_list(payload, "provider_article_keys_json")',
        "if not summary:\n        return",
        '_required_page_text(summary, "canonical_item_key")',
        '_required_page_nonnegative_int(summary, "duplicate_observation_count")',
        "not isinstance(value, int)",
        "isinstance(value, bool)",
        "news_page_row_payload_required",
        "news_page_row_payload_invalid",
    }
    forbidden = {
        'str(payload.get("canonical_item_key") or summary.get("canonical_item_key") or "")',
        'int(payload.get("duplicate_count") or summary.get("duplicate_observation_count") or 1)',
        'payload.get("source_ids_json") or summary.get("source_ids_json") or []',
        'payload.get("source_domains_json") or summary.get("source_domains_json") or []',
        'payload.get("provider_article_keys_json") or summary.get("provider_article_keys_json") or []',
        "number = int(value)",
        "except (TypeError, ValueError)",
    }
    assert sorted(token for token in required if token not in source) == []
    assert sorted(token for token in forbidden if token in source) == []


def test_news_page_search_text_has_no_legacy_alias_fallbacks() -> None:
    source = _read("src/parallax/domains/news_intel/types/news_page_search.py")
    forbidden = {
        'row.get("source_json") or row.get("source")',
        'row.get("source_ids_json") or row.get("source_ids")',
        'row.get("source_domains_json") or row.get("source_domains")',
        'row.get("token_lanes_json") or row.get("token_lanes")',
        'row.get("fact_lanes_json") or row.get("fact_lanes")',
    }

    assert sorted(token for token in forbidden if token in source) == []


def test_news_page_search_text_rejects_malformed_present_projection_fields() -> None:
    source = _read("src/parallax/domains/news_intel/types/news_page_search.py")
    build_source = _function_source(
        "src/parallax/domains/news_intel/types/news_page_search.py",
        "build_news_page_search_text",
    )
    required = {
        '_optional_json_object(row, "source_json")',
        '_optional_json_list(row, "source_ids_json")',
        '_optional_json_list(row, "source_domains_json")',
        '_optional_json_list(row, "token_lanes_json")',
        '_optional_json_list(row, "fact_lanes_json")',
        '_required_json_mapping(lane_value, field_name="token_lanes_json")',
        '_required_json_mapping(fact_value, field_name="fact_lanes_json")',
        "news_page_search_{field_name}_required",
    }
    forbidden = {
        "_json_object(row.get(",
        "_json_list(row.get(",
        "_json_object(lane_value)",
        "_json_object(fact_value)",
        "return {}",
        "return []",
    }

    assert sorted(token for token in required if token not in source) == []
    assert sorted(token for token in forbidden if token in build_source) == []


def test_news_high_signal_notification_uses_explicit_projected_identity_without_item_fallback() -> None:
    source = _function_source(
        "src/parallax/domains/notifications/services/notification_rules.py",
        "_news_high_signal_candidates",
    )
    semantic_source = _function_source(
        "src/parallax/domains/notifications/services/notification_rules.py",
        "_news_semantic_signature",
    )
    external_signature_source = _function_source(
        "src/parallax/domains/notifications/services/notification_rules.py",
        "_news_external_push_signature",
    )
    external_asset_bucket_source = _function_source(
        "src/parallax/domains/notifications/services/notification_rules.py",
        "_news_external_asset_bucket",
    )
    forbidden = {
        'row.get("news_item_id") or row.get("representative_news_item_id")',
        'row.get("representative_news_item_id") or news_item_id',
        'news_item_id = str(row.get("news_item_id") or "")',
        'representative_news_item_id = str(row.get("representative_news_item_id") or "")',
        "if not news_item_id or not representative_news_item_id:\n                continue",
        'story_key = str(row.get("story_key") or "")',
        'entity_type = "news_story" if story_key else "news_item"',
        'entity_key = f"news_story:{story_key}" if story_key else f"news_item:{news_item_id}"',
        "if not story_key:",
        'row.get("news_item_id") or "unknown"',
    }
    required = {
        'news_item_id = _required_news_text(row, "news_item_id")',
        'representative_news_item_id = _required_news_text(row, "representative_news_item_id")',
        'story_key = _required_news_text(row, "story_key")',
        'entity_type="news_story"',
        'entity_key=f"news_story:{story_key}"',
        'return _required_news_text(row, "news_item_id")',
    }
    combined = "\n".join((source, semantic_source, external_signature_source, external_asset_bucket_source))

    assert sorted(token for token in required if token not in combined) == []
    assert sorted(token for token in forbidden if token in combined) == []


def test_news_high_signal_notification_rejects_malformed_projected_payload_sections() -> None:
    source = _function_source(
        "src/parallax/domains/notifications/services/notification_rules.py",
        "_news_high_signal_candidates",
    )
    file_source = (ROOT / "src/parallax/domains/notifications/services/notification_rules.py").read_text(
        encoding="utf-8"
    )
    affected_source = _function_source(
        "src/parallax/domains/notifications/services/notification_rules.py",
        "_news_agent_affected_entities",
    )
    token_impacts_source = _function_source(
        "src/parallax/domains/notifications/services/notification_rules.py",
        "_news_token_impacts_payload",
    )
    body_source = _function_source(
        "src/parallax/domains/notifications/services/notification_rules.py",
        "_news_body",
    )
    helpers_source = "\n".join(
        _function_source("src/parallax/domains/notifications/services/notification_rules.py", function_name)
        for function_name in (
            "_required_news_mapping",
            "_required_news_list",
            "_required_news_list_mapping",
            "_required_news_positive_int",
            "_required_news_nonnegative_int",
            "_required_news_text",
            "_news_story_payload",
            "_news_market_scope_payload",
            "_news_agent_admission_payload",
            "_required_news_nested_text",
            "_required_news_nested_string_list",
            "_optional_news_nested_string_list",
            "_required_news_nested_mapping",
            "_required_news_nested_positive_int",
        )
    )
    required = {
        '_required_news_positive_int(row, "latest_at_ms")',
        'source_id = _required_news_text(row, "row_id")',
        '_required_news_mapping(row.get("signal"), "signal")',
        '_required_news_mapping(signal.get("alert_eligibility"), "alert_eligibility")',
        '_required_news_signal_true(eligibility, "in_app_eligible", section="alert_eligibility")',
        '_required_news_mapping(row.get("agent_brief"), "agent_brief")',
        '_required_news_list(row.get("token_impacts"), "token_impacts")',
        'story = _news_story_payload(row.get("story"))',
        'market_scope = _news_market_scope_payload(row.get("market_scope"))',
        'agent_admission = _news_agent_admission_payload(row.get("agent_admission"))',
        '_required_news_text(row, "source_domain")',
        '"canonical_url": _optional_news_text(row, "canonical_url")',
        '_optional_news_text(row, "canonical_url")',
        '_required_news_text(row, "agent_admission_status")',
        '_required_news_text(row, "agent_admission_reason")',
        "body = _news_body(row, summary=summary, source_domain=source_domain)",
        '_required_news_nonnegative_int(row, "duplicate_count")',
        '_required_news_list_mapping(item_value, "token_impacts")',
        '_required_news_list(agent_brief.get("affected_entities"), "agent_brief_affected_entities")',
        "news_high_signal_{field_name}_required",
        '_news_token_impact_optional_text(item, "symbol")',
        '_news_token_impact_optional_text(item, "target_symbol")',
        '_news_token_impact_optional_text(item, "market_type")',
        "_required_news_nested_text(",
        "_required_news_nested_string_list(",
        "_required_news_nested_mapping(",
        "_required_news_nested_positive_int(",
        '_optional_news_nested_string_list(payload, "story", field_name)',
        '"source_domains"',
    }
    forbidden = {
        "candidate": (
            'row.get("latest_at_ms") or row.get("agent_brief_computed_at_ms") or now_ms',
            'row.get("row_id") or news_item_id',
            '_dict(row.get("signal"))',
            '_dict(row.get("agent_brief"))',
            '_list(row.get("token_impacts"))',
            '_optional_news_mapping(row, "story")',
            '_dict(row.get("story"))',
            '_dict(row.get("market_scope"))',
            '_dict(row.get("agent_admission"))',
            '"source_domain": row.get("source_domain")',
            '"canonical_url": row.get("canonical_url")',
            '"agent_admission_status": row.get("agent_admission_status")',
            '"agent_admission_reason": row.get("agent_admission_reason")',
            'bool(eligibility.get("in_app_eligible"))',
            '_int(row.get("duplicate_count"))',
        ),
        "body": (
            "row.get('source_domain') or 'unknown'",
            'str(row.get("canonical_url") or "").strip()',
        ),
        "affected": (
            '_list(agent_brief.get("affected_entities"))',
            "return _list(",
        ),
        "token_impacts": (
            "if not isinstance(item, dict):\n            continue",
            "for item in _list(value):",
        ),
    }
    sources = {
        "candidate": source,
        "body": body_source,
        "affected": affected_source,
        "token_impacts": token_impacts_source,
    }
    offenders = [
        f"{source_name} contains {token}"
        for source_name, tokens in forbidden.items()
        for token in tokens
        if token in sources[source_name]
    ]

    combined = "\n".join((source, body_source, affected_source, token_impacts_source, helpers_source))
    assert sorted(token for token in required if token not in combined) == []
    assert offenders == []
    assert "def _optional_news_list(" not in file_source
    assert "**payload" not in _function_source(
        "src/parallax/domains/notifications/services/notification_rules.py",
        "_news_story_payload",
    )
    assert "**payload" not in _function_source(
        "src/parallax/domains/notifications/services/notification_rules.py",
        "_news_market_scope_payload",
    )
    assert "**payload" not in _function_source(
        "src/parallax/domains/notifications/services/notification_rules.py",
        "_news_agent_admission_payload",
    )


def test_news_high_signal_external_push_summary_has_no_market_read_fallback() -> None:
    summary_source = _function_source(
        "src/parallax/domains/notifications/services/notification_rules.py",
        "_news_agent_summary",
    )
    readiness_source = _function_source(
        "src/parallax/domains/notifications/services/notification_rules.py",
        "_news_external_push_readiness",
    )

    assert 'agent_brief.get("summary_zh")' in summary_source
    assert "isinstance(value, str)" in summary_source
    assert "_compact_text(value.strip(), limit=360)" in summary_source
    assert "agent_brief_missing_summary" in readiness_source
    assert "_optional_news_signal_bool(" in readiness_source
    assert '"external_push_ready"' in readiness_source
    assert "_required_news_external_push_basis(eligibility)" in readiness_source
    assert "_optional_news_signal_text(" in readiness_source
    assert '"external_push_block_reason"' in readiness_source
    assert 'section="alert_eligibility"' in readiness_source
    assert "market_read_zh" not in summary_source
    assert 'agent_brief.get("summary_zh") or' not in summary_source
    assert "str(" not in summary_source
    assert 'eligibility.get("external_push_ready") is not True' not in readiness_source
    assert 'str(eligibility.get("external_push_block_reason") or "external_push_state_missing")' not in readiness_source
    assert 'eligibility.get("external_push_basis") or' not in readiness_source
    assert readiness_source.index("block_reason = _optional_news_signal_text(") < readiness_source.index(
        "if external_push_ready is not True:"
    )


def test_news_high_signal_external_push_signature_uses_ready_brief_direction_without_display_signal_fallback() -> None:
    readiness_source = _function_source(
        "src/parallax/domains/notifications/services/notification_rules.py",
        "_news_external_push_readiness",
    )
    signature_source = _function_source(
        "src/parallax/domains/notifications/services/notification_rules.py",
        "_news_external_push_signature",
    )

    assert "agent_brief_missing_direction" in readiness_source
    assert "agent_brief_missing_decision_class" in readiness_source
    assert '_required_news_agent_text(agent_brief, "direction")' in signature_source
    assert 'agent_brief.get("direction")' not in signature_source
    assert 'display_signal.get("direction")' not in signature_source
    assert "_news_display_signal(row)" not in signature_source


def test_news_high_signal_agent_brief_status_requires_explicit_text_without_pending_repair() -> None:
    ready_source = _function_source(
        "src/parallax/domains/notifications/services/notification_rules.py",
        "_ready_news_agent_brief",
    )

    assert "_required_news_agent_status(agent_brief)" in ready_source
    assert 'str(agent_brief.get("status") or "")' not in ready_source


def test_news_high_signal_public_agent_brief_requires_typed_text_without_payload_passthrough() -> None:
    public_source = _function_source(
        "src/parallax/domains/notifications/services/notification_rules.py",
        "_public_news_agent_brief",
    )

    assert "_required_news_agent_status(agent_brief)" in public_source
    assert "_news_agent_optional_text(agent_brief, key)" in public_source
    assert "agent_brief[key]" not in public_source


def test_news_high_signal_public_affected_entity_requires_typed_fields_without_passthrough() -> None:
    source = _function_source(
        "src/parallax/domains/notifications/services/notification_rules.py",
        "_public_news_affected_entity",
    )

    assert "_news_affected_entity_optional_text(entity, key)" in source
    assert '_news_affected_entity_optional_string_list(entity, "evidence_refs")' in source
    assert "entity[key]" not in source


def test_news_high_signal_affected_entity_symbols_use_formal_symbol_only() -> None:
    source = _function_source(
        "src/parallax/domains/notifications/services/notification_rules.py",
        "_news_affected_entity_symbols",
    )

    assert '_news_affected_entity_optional_text(entity, "symbol")' in source
    assert '"ticker"' not in source
    assert '"asset"' not in source
    assert 'for field_name in ("symbol", "ticker", "asset")' not in source


def test_news_high_signal_ready_brief_public_signal_fields_do_not_use_projection_fallbacks() -> None:
    candidate_source = _function_source(
        "src/parallax/domains/notifications/services/notification_rules.py",
        "_news_high_signal_candidates",
    )
    semantic_source = _function_source(
        "src/parallax/domains/notifications/services/notification_rules.py",
        "_news_semantic_signature",
    )
    helper_source = _function_source(
        "src/parallax/domains/notifications/services/notification_rules.py",
        "_news_notification_signal_fields",
    )

    forbidden = {
        "candidate": (
            'eligibility.get("decision_class") or ready_agent_brief.get("decision_class")',
            'agent_brief.get("direction") or display_signal.get("direction")',
        ),
        "semantic": (
            'agent_brief.get("decision_class") or eligibility.get("decision_class")',
            'agent_brief.get("direction") or display_signal.get("direction")',
        ),
    }
    offenders = [
        f"{source_name} contains {token}"
        for source_name, tokens in forbidden.items()
        for token in tokens
        if token in {"candidate": candidate_source, "semantic": semantic_source}[source_name]
    ]

    assert "if ready_agent_brief:" in helper_source
    assert '_news_agent_required_text(ready_agent_brief, "decision_class")' in helper_source
    assert '_news_agent_required_text(ready_agent_brief, "direction")' in helper_source
    assert offenders == []


def test_news_high_signal_pending_signal_fields_require_projected_text_without_string_repair() -> None:
    helper_source = _function_source(
        "src/parallax/domains/notifications/services/notification_rules.py",
        "_news_notification_signal_fields",
    )

    assert '_required_news_signal_text(eligibility, "decision_class", section="alert_eligibility")' in helper_source
    assert "_required_news_signal_direction(signal=signal, display_signal=display_signal)" in helper_source
    assert 'str(eligibility.get("decision_class") or "")' not in helper_source
    assert 'str(display_signal.get("direction") or signal.get("direction") or "")' not in helper_source


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


def test_news_page_projection_requires_story_payload_without_item_fallback() -> None:
    projection_path = "src/parallax/domains/news_intel/services/news_page_projection.py"
    repository_path = "src/parallax/domains/news_intel/repositories/news_repository.py"
    worker_path = "src/parallax/domains/news_intel/runtime/news_page_projection_worker.py"
    build_source = _function_source(projection_path, "build_news_page_row")
    story_source = _function_source(projection_path, "_story_payload")
    positive_int_source = _function_source(projection_path, "_positive_int")
    repository_loader_source = _function_source(repository_path, "load_story_projection_payloads_for_items")
    repository_story_source = _function_source(repository_path, "_story_projection_payload")
    projection_parts_source = _function_source(worker_path, "_projection_parts")
    member_ids_source = _function_source(worker_path, "_member_news_item_ids")
    member_id_helper_source = _function_source(worker_path, "_required_member_news_item_id")
    forbidden = {
        "story or {}",
        'item.get("story_key")',
        'story_payload.get("story_key") or',
        'story_payload.get("representative_news_item_id") or',
        'story_payload.get("member_count") or 1',
        'payload.get("item") or payload',
        'payload.get("token_mentions") or []',
        'payload.get("fact_candidates") or []',
        'payload.get("member_items") or []',
        'representative.get("token_mentions") or []',
        'representative.get("fact_candidates") or []',
        'story.get("member_news_item_ids") or []',
        '_json_list(story.get("source_ids"))',
        '_json_list(story.get("provider_article_keys"))',
        'member_ids = [str(item["news_item_id"])]',
        'row.get("news_item_id") or ""',
    }
    repository_forbidden = {
        '_json_dict(payload.get("item"))',
        'item.get("news_item_id") or ""',
        '_json_list(item.get("source_ids_json")) or [item.get("source_id")]',
        '_json_list(item.get("source_domains_json")) or [item.get("source_domain")]',
        'int(item.get("published_at_ms") or 0)',
        'member_news_item_ids[0] if member_news_item_ids else ""',
        'member_items[0].get("story_identity_json")) if member_items else {}',
    }
    combined = "\n".join(
        (
            build_source,
            story_source,
            repository_loader_source,
            repository_story_source,
            projection_parts_source,
            member_ids_source,
            member_id_helper_source,
        )
    )

    assert sorted(token for token in forbidden if token in combined) == []
    assert sorted(token for token in repository_forbidden if token in repository_story_source) == []
    assert "news_page_projection_story_required" in story_source
    assert "not isinstance(value, int)" in positive_int_source
    assert "int(value)" not in positive_int_source
    assert '_optional_story_list(story, "source_ids"' in story_source
    assert '_optional_story_list(story, "provider_article_keys"' in story_source
    assert "_required_story_projection_member_item(payload)" in repository_story_source
    assert '_required_story_projection_text(item, "news_item_id")' in repository_story_source
    assert '_required_story_projection_list(item, "source_ids_json")' in repository_story_source
    assert '_required_story_projection_list(item, "source_domains_json")' in repository_story_source
    assert '_required_story_projection_list(item, "provider_article_keys_json")' in repository_story_source
    assert '_required_story_projection_nonnegative_int(item, "published_at_ms")' in repository_story_source
    assert '_required_story_projection_mapping(member_items[0], "story_identity_json")' in repository_story_source
    assert '_required_story_projection_payload_list(representative, "token_mentions")' in repository_loader_source
    assert '_required_story_projection_payload_list(representative, "fact_candidates")' in repository_loader_source
    assert '_required_mapping(payload, "item")' in projection_parts_source
    assert '_required_mapping(payload, "story")' in projection_parts_source
    assert '_required_mapping_list(payload, "member_items")' in projection_parts_source
    assert "_required_member_news_item_id(row, item=item)" in member_ids_source
    assert "news_page_projection_member_item_news_item_id_required" in member_id_helper_source


def test_news_page_projection_timing_fields_require_typed_int_without_repair() -> None:
    projection_path = "src/parallax/domains/news_intel/services/news_page_projection.py"
    build_source = _function_source(projection_path, "build_news_page_row")
    agent_brief_source = _function_source(projection_path, "_compact_agent_brief")
    optional_int_source = _function_source(projection_path, "_optional_int")
    combined = "\n".join((build_source, agent_brief_source, optional_int_source))
    required = {
        '"computed_at_ms": _required_positive_int(',
        'field_name="computed_at_ms"',
        'field_name="agent_brief_computed_at_ms"',
        "not isinstance(value, int)",
        "isinstance(value, bool)",
        "value <= 0",
    }
    forbidden = {
        '"computed_at_ms": int(computed_at_ms)',
        "return int(value)",
    }

    assert sorted(token for token in required if token not in combined) == []
    assert sorted(token for token in forbidden if token in combined) == []


def test_news_page_projection_loader_requires_explicit_arrays_without_json_list_defaults() -> None:
    repository_path = "src/parallax/domains/news_intel/repositories/news_repository.py"
    source = _function_source(repository_path, "load_items_for_page_projection")
    helper_sources = "\n".join(
        _function_source(repository_path, function_name)
        for function_name in (
            "_required_page_projection_input_list",
            "_required_repository_json_list",
        )
    )
    forbidden = {
        '_json_list(row["token_mentions"])',
        '_json_list(row["fact_candidates"])',
    }
    required = {
        '_required_page_projection_input_list(row, "token_mentions")',
        '_required_page_projection_input_list(row, "fact_candidates")',
        "news_page_projection_input_evidence",
        'raise ValueError(f"{error_prefix}_required:{field_name}")',
        'raise ValueError(f"{error_prefix}_invalid:{field_name}")',
    }

    assert sorted(token for token in forbidden if token in source) == []
    assert sorted(token for token in required if token not in source and token not in helper_sources) == []


def test_news_page_projection_requires_explicit_item_admission_and_market_scope() -> None:
    projection_path = "src/parallax/domains/news_intel/services/news_page_projection.py"
    source = "\n".join(
        _function_source(projection_path, function_name)
        for function_name in (
            "build_news_page_row",
            "_market_scope_payload",
            "_agent_admission_payload",
            "_required_item_text",
            "_required_item_mapping",
            "_required_item_list",
            "_required_payload_text",
            "_required_payload_list",
            "_required_payload_mapping",
            "_optional_payload_mapping",
            "_require_matching_agent_admission",
            "_agent_signal_payload",
        )
    )
    forbidden = {
        'item.get("agent_admission_status") or "needs_review"',
        'item.get("agent_admission_reason") or ""',
        'item.get("agent_representative_news_item_id") or representative_news_item_id',
        'agent_admission.get("representative_news_item_id") or representative_news_item_id',
        '_json_object(item.get("market_scope_json"))',
        '_json_object(item.get("agent_admission_json"))',
        '_json_list(item.get("content_tags_json"))',
        '_json_object(item.get("content_classification_json"))',
        '"content_class": item.get("content_class")',
        'payload = {"status": status, "reason": reason}',
        'payload.get("status") or status or "needs_review"',
        'payload.get("reason") or reason or ""',
        'payload.get("representative_news_item_id") or representative_news_item_id',
        '_json_object(admission.get("basis"))',
    }
    required = {
        '_required_item_text(item, "agent_admission_status"',
        '_required_item_text(item, "agent_admission_reason"',
        '_required_item_text(\n        item,\n        "agent_representative_news_item_id"',
        '_required_item_mapping(item, "market_scope_json"',
        '_required_item_mapping(item, "agent_admission_json"',
        '_required_item_text(item, "content_class"',
        '_required_item_list(item, "content_tags_json"',
        '_required_item_mapping(item, "content_classification_json"',
        "_require_matching_agent_admission(",
        '_required_payload_mapping(\n        admission,\n        "basis"',
        '_optional_payload_mapping(\n        basis,\n        "similar_story"',
        '_optional_payload_mapping(\n        basis,\n        "exact_duplicate"',
        "news_page_projection_item_{field_name}_required",
        "news_page_projection_{payload_name}_{field_name}_required",
    }

    assert sorted(token for token in forbidden if token in source) == []
    assert sorted(token for token in required if token not in source) == []


def test_news_page_projection_agent_status_has_no_secondary_pending_fallback() -> None:
    projection_path = "src/parallax/domains/news_intel/services/news_page_projection.py"
    source = "\n".join(
        _function_source(projection_path, function_name)
        for function_name in (
            "build_news_page_row",
            "_page_signal",
            "_signal_with_independent_state",
            "_required_agent_signal_status",
            "_required_agent_signal_text",
            "_alert_eligible",
            "_external_push_readiness",
        )
    )
    forbidden = {
        'str(agent_payload.get("status") or "pending")',
        'str(agent_signal.get("status") or "pending")',
        'agent_signal.get("direction") or "neutral"',
        'str(agent_signal.get("decision_class") or "")',
    }
    required = {
        "_required_agent_signal_status(agent_payload, news_item_id=news_item_id)",
        "_required_agent_signal_status(agent_signal)",
        '_required_agent_signal_text(agent_signal, "direction")',
        '_required_agent_signal_text(agent_signal, "decision_class")',
        "news_page_projection_agent_signal_status_required",
        "news_page_projection_agent_signal_{field_name}_required",
    }

    assert sorted(token for token in forbidden if token in source) == []
    assert sorted(token for token in required if token not in source) == []


def test_news_story_brief_packet_requires_story_context_without_item_fallback() -> None:
    packet_source = _read("src/parallax/domains/news_intel/services/news_story_brief_input.py")
    worker_candidate_list_source = _function_source(
        "src/parallax/domains/news_intel/runtime/news_story_brief_worker.py",
        "_candidate_list_of_dicts",
    )
    worker_candidate_index_source = _function_source(
        "src/parallax/domains/news_intel/runtime/news_story_brief_worker.py",
        "_candidates_by_story_key",
    )
    story_target_source = _function_source(
        "src/parallax/domains/news_intel/repositories/news_repository.py",
        "load_story_brief_targets",
    )
    combined = "\n".join(
        (
            packet_source,
            worker_candidate_list_source,
            worker_candidate_index_source,
            story_target_source,
        )
    )

    forbidden = {
        "member_items or [representative_item]",
        'representative_item,\n        "agent_admission_json"',
        'story.get("event_type") or representative_item.get("event_type")',
        'story.get("market_scope_json") or representative_item.get("market_scope_json")',
        'elif "market_scope" in story and story["market_scope"] is not None:',
        'value.get("market_scope")',
        'value.get("market_scope_primary")',
        "if isinstance(value, list | tuple | set)",
        "if isinstance(value, str)",
        'representative["item"].get("story_identity_version") or NEWS_STORY_IDENTITY_VERSION',
        'representative["item"].get("market_scope_json") or []',
        'representative["item"].get("agent_admission_json") or {}',
        'candidate.get("story", {})',
        'if isinstance(candidate.get("story"), Mapping)',
        "if value is None:\n        return []",
        '_context_object(story, "similarity_json", "similarity")',
        '_context_object(story, "material_delta_json", "material_delta")',
        'agent_admission.get("material_delta") or basis.get("material_delta")',
        'basis.get("similarity")',
        '_required_context_object(story, "story_identity_json", "story_identity")',
        '_required_context_object(story, "agent_admission_json", "agent_admission")',
        "_int(row.get(field_name))",
        '_json_list(row["entities"])',
        '_json_list(row["token_mentions"])',
        '_json_list(row["fact_candidates"])',
    }
    required = {
        '_required_context_object(story, "agent_admission_json", alias_key="agent_admission")',
        '_required_context_object(story, "story_identity_json", alias_key="story_identity")',
        '_optional_context_object(story, "similarity_json", alias_key="similarity")',
        '_optional_context_object(story, "material_delta_json", alias_key="material_delta")',
        'raise ValueError(f"news_story_brief_{json_key}_required")',
        "_required_market_scope(story)",
        'scope = value.get("scope")',
        'primary = value.get("primary")',
        "_required_member_rows(member_items)",
        "news_story_brief_member_news_item_id_required",
        "_required_positive_int(",
        "not isinstance(value, int)",
        "isinstance(value, bool)",
        "news_story_brief_representative_published_at_ms_required",
        "news_story_brief_member_published_at_ms_required",
        '_required_story_item_json_value(representative_item, "market_scope_json")',
        '_required_story_item_mapping(\n                representative_item,\n                "agent_admission_json"',
        'raise RuntimeError(f"news_story_brief_candidate_{field}_array_required")',
        '_story_brief_target_list(row, "entities")',
        '_story_brief_target_list(row, "token_mentions")',
        '_story_brief_target_list(row, "fact_candidates")',
        '_required_candidate_text(story, field="story_key")',
    }

    assert sorted(token for token in forbidden if token in combined) == []
    assert sorted(token for token in required if token not in combined) == []


def test_news_story_brief_worker_restores_started_failed_runs_without_model_fallback() -> None:
    path = "src/parallax/domains/news_intel/runtime/news_story_brief_worker.py"
    source = _read(path)
    current_source = _function_source(path, "_current_brief_is_fresh")
    fresh_failed_source = _function_source(path, "_fresh_failed_run")
    restore_completed_source = _function_source(path, "_restore_current_from_completed_run")
    restore_source = _function_source(path, "_restore_current_from_failed_run")
    current_text_source = _function_source(path, "_required_current_text")
    current_status_source = _function_source(path, "_required_current_status")
    completed_payload_source = _function_source(path, "_required_completed_run_payload")
    publishable_summary_source = _function_source(path, "_publishable_summary")
    run_status_source = _function_source(path, "_required_run_status")
    run_text_source = _function_source(path, "_required_run_text")
    optional_dict_source = _function_source(path, "_optional_dict")
    audit_latency_source = _function_source(path, "_required_audit_latency_ms")
    audit_mapping_source = _function_source(path, "_required_audit_mapping")
    insert_run_source = _function_source(path, "_insert_run")
    provider_failure_source = _function_source(path, "_insert_failed_provider_run")
    failed_error_source = _function_source(path, "_required_failed_run_error_class")
    failed_message_source = _function_source(path, "_required_failed_run_error")
    failed_run_errors_source = _function_source(path, "_failed_run_errors")
    finished_at_source = _function_source(path, "_required_run_finished_at_ms")
    outcome_source = _function_source(path, "_required_run_outcome")
    execution_started_source = _function_source(path, "_required_run_execution_started")
    reason_source = _function_source(path, "_reason_value")

    required = {
        "_fresh_failed_run(candidate, packet=packet, agent_config=agent_config)",
        'notes["restored_from_failed_run"]',
        '_required_current_text(current, "story_brief_key", expected=packet.story_brief_key)',
        '_required_current_text(current, "agent_run_id")',
        "_required_current_status(current)",
        "news_story_brief_current_{field}_required",
        "news_story_brief_current_status_required",
        "_required_completed_run_payload(run, outcome=outcome)",
        "news_story_brief_run_response_json_required:completed_run",
        "news_story_brief_run_response_status_required:completed_run",
        "news_story_brief_run_publishable_summary_required:completed_run",
        'payload["summary_zh"]',
        "return dict(value)",
        "_required_run_status(run)",
        '_required_run_text(run, "story_brief_key", reason="completed_run", expected=packet.story_brief_key)',
        '_required_run_text(run, "story_brief_key", reason="failed_run", expected=packet.story_brief_key)',
        '_required_run_text(run, "input_hash", reason="completed_run")',
        '_required_run_text(run, "input_hash", reason="failed_run")',
        'f"news_story_brief_run_{field}_required:{reason}"',
        "_required_audit_latency_ms(audit)",
        '_required_audit_mapping(audit, "trace_metadata")',
        '_required_audit_mapping(audit, "usage")',
        "news_story_brief_audit_{field_name}_required",
        "news_story_brief_audit_latency_ms_required",
        'audit["latency_ms"] = max(0, int(finished_at_ms) - int(started_at_ms))',
        '_required_run_id(run, reason="failed_run")',
        'status = str(completed_run["outcome"])',
        '_required_run_outcome(run, reason="completed_run", allowed={"ready", "insufficient"})',
        '_required_run_outcome(run, reason="failed_run", allowed={"failed"})',
        "news_story_brief_run_outcome_required",
        '_required_run_finished_at_ms(run, reason="completed_run")',
        '_required_run_finished_at_ms(run, reason="failed_run")',
        "news_story_brief_run_finished_at_ms_required",
        "if value <= 0:",
        "_required_failed_run_error_class(run)",
        "_required_failed_run_error(run)",
        "news_story_brief_run_error_class_required:failed_run",
        "news_story_brief_run_error_required:failed_run",
        "_failed_brief(_failed_run_errors(run), terminal_reason=error_class)",
        '_required_run_execution_started(run, reason="failed_run")',
        "news_story_brief_run_execution_started_required",
        "def _reason_value(reason: AgentExecutionErrorClass) -> str:",
        "return reason.value",
    }
    forbidden = {
        "story_failed_run_fallback",
        'completed_run.get("outcome") or "ready"',
        'str(run.get("status") or "")',
        'run.get("outcome") or ""',
        'str(run.get("story_brief_key") or "")',
        'str(run.get("input_hash") or "")',
        'str(run.get("artifact_version_hash") or "")',
        'str(run.get("prompt_version") or "")',
        'str(run.get("schema_version") or "")',
        'str(run.get("validator_version") or "")',
        'audit.get("latency_ms") or 0',
        '_dict(audit.get("trace_metadata"))',
        '_dict(audit.get("usage"))',
        'run.get("run_id") or',
        'int(run.get("finished_at_ms") or self.clock_ms())',
        'run.get("error_class") or "story_brief_failed"',
        'run.get("error") or error_class',
        'run.get("story_brief_key") or packet.story_brief_key',
        'current.get("status") or ""',
        'current.get("input_hash") or ""',
        'current.get("artifact_version_hash") or ""',
        'current.get("prompt_version") or ""',
        'current.get("schema_version") or ""',
        'current.get("validator_version") or ""',
        "if payload is None:\n        return None",
        'str(payload.get("status") or "") != outcome',
        'payload.get("market_read_zh")',
        'payload.get("summary_zh") or',
        "def _dict(",
        "return {}",
        'if outcome == "ready" and not _publishable_summary(payload):\n        return None',
        'getattr(reason, "value", reason)',
        "return str(value) if value else None",
        'if not bool(run.get("execution_started")):',
        'run.get("execution_started")',
    }

    combined = "\n".join(
        (
            source,
            current_source,
            fresh_failed_source,
            restore_completed_source,
            restore_source,
            current_text_source,
            current_status_source,
            completed_payload_source,
            publishable_summary_source,
            run_status_source,
            run_text_source,
            optional_dict_source,
            audit_latency_source,
            audit_mapping_source,
            insert_run_source,
            provider_failure_source,
            failed_error_source,
            failed_message_source,
            failed_run_errors_source,
            finished_at_source,
            outcome_source,
            execution_started_source,
            reason_source,
        )
    )
    assert sorted(token for token in required if token not in combined) == []
    assert sorted(token for token in forbidden if token in combined) == []
    assert "not isinstance(value, int)" in finished_at_source
    assert "int(value)" not in finished_at_source


def test_news_story_brief_worker_requires_claim_contract_without_target_id_fallback() -> None:
    path = "src/parallax/domains/news_intel/runtime/news_story_brief_worker.py"
    source = _read(path)
    claim_story_key_source = _function_source(path, "_required_story_brief_target_story_key")
    claim_text_source = _function_source(path, "_require_claim_text")
    claim_window_source = _function_source(path, "_require_claim_empty_window")
    combined = "\n".join((claim_story_key_source, claim_text_source, claim_window_source))

    required = {
        "_required_story_brief_target_story_key(target)",
        '_require_claim_text(target, field="projection_name", expected=STORY_BRIEF_INPUT)',
        '_require_claim_text(target, field="target_kind", expected="story")',
        "_require_claim_empty_window(target)",
        'return _require_claim_text(target, field="target_id")',
        'f"news_story_brief_claim_{field}_required"',
        "news_story_brief_claim_window_empty_required",
        "if not isinstance(value, str):",
    }
    forbidden = {
        'target.get("target_id") or ""',
        'str(target.get("target_id")',
        'target_id", "")',
    }

    assert sorted(token for token in required if token not in source + combined) == []
    assert sorted(token for token in forbidden if token in source) == []


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
