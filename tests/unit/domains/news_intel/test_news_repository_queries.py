from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

from parallax.domains.news_intel._constants import (
    NEWS_ITEM_AGENT_ADMISSION_VERSION,
    NEWS_MARKET_SCOPE_VERSION,
    NEWS_PAGE_PROJECTION_VERSION,
)
from parallax.domains.news_intel.repositories.news_item_repository import NewsItemRepository
from parallax.domains.news_intel.repositories.news_page_repository import NewsPageRepository
from parallax.domains.news_intel.repositories.news_repository_support import (
    _current_policy_material_duplicate_groups,
    _news_item_aggregate_changed,
    news_source_config_payload_hash,
)
from parallax.domains.news_intel.repositories.news_source_repository import NewsSourceRepository
from parallax.domains.news_intel.repositories.news_story_agent_repository import NewsStoryAgentRepository
from parallax.domains.news_intel.types.news_item_agent_admission import NewsItemAgentAdmission
from parallax.domains.news_intel.types.news_market_scope import NewsMarketScope
from parallax.domains.news_intel.types.news_story_identity import NEWS_STORY_IDENTITY_VERSION, NewsStoryIdentity


def test_page_projection_loader_reads_source_payload_for_claimed_targets() -> None:
    conn = CapturingConnection()
    repo = NewsPageRepository(conn)

    rows = repo.load_items_for_page_projection(news_item_ids=["news-1"])

    assert rows == []
    assert "WHERE items.news_item_id = ANY(%s::text[])" in conn.sql
    assert "{_NEWS_ITEM_WORKER_COLUMNS_SQL}" not in conn.sql
    assert "{_NEWS_ITEM_WORKER_JSON_SQL}" not in conn.sql
    assert "SELECT items.*" not in conn.sql
    assert "to_jsonb(items.*)" not in conn.sql
    assert "JOIN LATERAL" in conn.sql
    assert "edge_sources.enabled = true" in conn.sql
    assert "'provider_type', source_rep.provider_type" in conn.sql
    assert "'source_quality_status', source_rep.source_quality_status" in conn.sql
    assert "'coverage_tags_json', source_rep.coverage_tags_json" in conn.sql
    assert "news_story_members" not in conn.sql
    assert "news_story_groups" not in conn.sql
    assert "news_item_agent_briefs" not in conn.sql
    assert "current_brief" not in conn.sql


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [
        ("token_mentions", None),
        ("token_mentions", {}),
        ("fact_candidates", None),
        ("fact_candidates", {}),
    ],
)
def test_page_projection_loader_rejects_malformed_evidence_arrays_without_json_list_defaults(
    field_name: str,
    bad_value: object,
) -> None:
    row = _valid_page_projection_loader_row()
    row[field_name] = bad_value
    conn = NewsPageRowsConnection(rows=[row])
    repo = NewsPageRepository(conn)

    with pytest.raises(ValueError, match=f"news_page_projection_input_evidence.*{field_name}"):
        repo.load_items_for_page_projection(news_item_ids=["news-1"])


@pytest.mark.parametrize(
    "source_updated_at_ms",
    [
        pytest.param(None, id="none"),
        pytest.param(0, id="zero"),
        pytest.param(-1, id="negative"),
        pytest.param(True, id="bool"),
        pytest.param("10", id="string"),
    ],
)
def test_story_brief_targets_require_positive_source_updated_at(source_updated_at_ms: object) -> None:
    row = _valid_story_brief_target_row()
    row["source_updated_at_ms"] = source_updated_at_ms
    conn = StoryBriefTargetsConnection(rows=[row])

    with pytest.raises(ValueError, match="news_story_brief_target_source_updated_at_ms_required"):
        NewsStoryAgentRepository(conn).load_story_brief_targets(story_keys=["story:news-1"])


def test_story_brief_target_loader_emits_formal_story_identity_json_without_alias() -> None:
    row = _valid_story_brief_target_row()
    conn = StoryBriefTargetsConnection(rows=[row])
    repo = NewsStoryAgentRepository(conn)

    targets = repo.load_story_brief_targets(story_keys=["story:news-1"])

    assert len(targets) == 1
    story = targets[0]["story"]
    assert story["story_identity_json"] == _valid_story_identity_payload()
    assert "story_identity" not in story


def test_news_item_source_watermarks_for_sources_reads_persisted_item_times() -> None:
    conn = CapturingConnection()
    repo = NewsSourceRepository(conn)

    rows = repo.list_news_item_source_watermarks_for_sources(source_ids=["source-1"])

    assert rows == []
    assert "JOIN news_items AS items ON items.news_item_id = edges.news_item_id" in conn.sql
    assert "items.published_at_ms" in conn.sql
    assert "items.fetched_at_ms" in conn.sql
    assert "source_watermark_ms" in conn.sql
    assert "clock_timestamp" not in conn.sql
    assert "now_ms" not in conn.sql


def test_news_item_source_watermarks_reads_persisted_item_times_without_worker_clock() -> None:
    conn = CapturingConnection()
    repo = NewsSourceRepository(conn)

    rows = repo.list_news_item_source_watermarks(news_item_ids=["news-1"])

    assert rows == []
    assert "FROM news_items AS items" in conn.sql
    assert "items.published_at_ms" in conn.sql
    assert "items.fetched_at_ms" in conn.sql
    assert "source_watermark_ms" in conn.sql
    assert "clock_timestamp" not in conn.sql
    assert "now_ms" not in conn.sql


def test_canonical_rebuild_list_reads_only_current_servable_news_items() -> None:
    conn = CapturingConnection()
    repo = NewsItemRepository(conn)

    rows = repo.list_news_items_for_canonical_rebuild(limit=25)

    assert rows == []
    assert "FROM news_items AS items" in conn.sql
    assert "items.lifecycle_status = 'processed'" in conn.sql
    assert "items.story_key <> ''" in conn.sql
    assert "items.story_identity_version = %s" in conn.sql
    assert "JOIN news_sources AS edge_sources ON edge_sources.source_id = edges.source_id" in conn.sql
    assert "edge_sources.enabled = true" in conn.sql
    assert "source_watermark_ms > 0" in conn.sql
    assert conn.params == (NEWS_STORY_IDENTITY_VERSION, 25)


@pytest.mark.parametrize("limit", [-1, True, "25"])
def test_canonical_rebuild_list_rejects_malformed_limit_before_sql(limit: object) -> None:
    conn = CapturingConnection()
    repo = NewsItemRepository(conn)

    with pytest.raises(ValueError, match="news_canonical_rebuild_limit_required"):
        repo.list_news_items_for_canonical_rebuild(limit=limit)  # type: ignore[arg-type]

    assert conn.statements == []


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [
        pytest.param("sync_high_watermark_ms", None, id="missing_high_watermark"),
        pytest.param("sync_high_watermark_ms", -1, id="negative_high_watermark"),
        pytest.param("sync_high_watermark_ms", True, id="bool_high_watermark"),
        pytest.param("sync_high_watermark_ms", "0", id="string_high_watermark"),
        pytest.param("sync_overlap_ms", None, id="missing_overlap"),
        pytest.param("sync_overlap_ms", -1, id="negative_overlap"),
        pytest.param("sync_overlap_ms", False, id="bool_overlap"),
        pytest.param("sync_overlap_ms", "0", id="string_overlap"),
    ],
)
def test_source_sync_cursor_requires_explicit_nonnegative_sync_scalars(
    field_name: str,
    bad_value: object,
) -> None:
    row = {
        "sync_cursor_json": {"page": "cursor"},
        "sync_high_watermark_ms": 0,
        "sync_overlap_ms": 0,
        "sync_diagnostics_json": {"stop_reason": "caught_up"},
    }
    row[field_name] = bad_value
    conn = SourceSyncCursorConnection(row=row)
    repo = NewsSourceRepository(conn)

    with pytest.raises(ValueError, match=f"news_source_sync_cursor_{field_name}_required"):
        repo.source_sync_cursor("source-1")


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [
        ("entities", {"entity_id": "entity-1"}),
        ("token_mentions", {"mention_id": "mention-1"}),
        ("fact_candidates", {"fact_candidate_id": "fact-1"}),
    ],
)
def test_story_brief_target_loader_rejects_malformed_member_evidence_arrays(
    field_name: str,
    bad_value: object,
) -> None:
    row = _valid_story_brief_target_row()
    row[field_name] = bad_value
    conn = StoryBriefTargetsConnection(rows=[row])
    repo = NewsStoryAgentRepository(conn)

    with pytest.raises(ValueError, match=f"news_story_brief_target_{field_name}_required"):
        repo.load_story_brief_targets(story_keys=["story:news-1"])


def test_agent_admission_context_loader_uses_narrow_news_item_payloads() -> None:
    conn = CapturingConnection()
    repo = NewsItemRepository(conn)

    rows = repo.load_agent_admission_contexts(news_item_ids=["news-1"], now_ms=1_000)

    assert rows == []
    assert "WITH target_ids(news_item_id, ordinal) AS" in conn.sql
    assert "SELECT items.*" not in conn.sql
    assert "to_jsonb(items.*)" not in conn.sql
    assert "SELECT *" not in conn.sql
    assert "'news_item_id', items.news_item_id" in conn.sql
    assert "'content_classification_json', items.content_classification_json" in conn.sql
    assert "'source_enabled', sources.enabled" in conn.sql
    assert "duplicate_candidate_ids" in conn.sql
    assert "story_candidate_ids" in conn.sql
    assert "UNION" in conn.sql
    assert "url_items.canonical_url <> ''" in conn.sql
    assert "canonical_key_items.canonical_item_key <> ''" in conn.sql
    assert "content_hash_items.content_hash <> ''" in conn.sql
    assert "story_key_items.story_key <> ''" in conn.sql
    assert "title_fingerprint_items.title_fingerprint <> ''" in conn.sql
    assert "duplicate_items.canonical_url = items.canonical_url" not in conn.sql
    assert "story_items.story_key = items.story_key" not in conn.sql


def test_agent_admission_context_provider_duplicate_lookup_uses_observation_edges() -> None:
    conn = CapturingConnection()
    repo = NewsItemRepository(conn)

    rows = repo.load_agent_admission_contexts(news_item_ids=["news-1"], now_ms=1_000)

    assert rows == []
    assert "target_provider_edges" in conn.sql
    assert "duplicate_edges.provider_article_key = target_provider_edges.provider_article_key" in conn.sql
    assert "jsonb_array_elements_text" not in conn.sql


def test_agent_admission_representative_current_state_uses_story_briefs() -> None:
    conn = CapturingConnection()
    repo = NewsItemRepository(conn)

    rows = repo.load_agent_admission_contexts(news_item_ids=["news-1"], now_ms=1_000)

    assert rows == []
    exact_duplicate_section = conn.sql.split(") AS exact_duplicates ON true", 1)[0]
    story_candidate_section = conn.sql.split(") AS exact_duplicates ON true", 1)[1].split(
        ") AS story_candidates ON true",
        1,
    )[0]
    assert "LEFT JOIN news_story_agent_briefs AS duplicate_story_current_brief" in exact_duplicate_section
    assert "duplicate_story_current_brief.story_brief_key IS NOT NULL" in exact_duplicate_section
    assert "news_item_agent_briefs AS duplicate_current_brief" not in exact_duplicate_section
    assert "LEFT JOIN news_story_agent_briefs AS story_current_brief" in story_candidate_section
    assert "story_current_brief.story_brief_key" in story_candidate_section
    assert "news_item_agent_briefs AS story_current_brief" not in story_candidate_section


def test_agent_admission_context_loader_does_not_read_target_item_current_brief_audit_rows() -> None:
    conn = CapturingConnection()
    repo = NewsItemRepository(conn)

    rows = repo.load_agent_admission_contexts(news_item_ids=["news-1"], now_ms=1_000)

    assert rows == []
    assert "news_item_agent_briefs AS current_brief" not in conn.sql
    assert "_CURRENT_NEWS_ITEM_BRIEF_CURRENT_BRIEF_SQL" not in conn.sql


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [
        ("entities", None),
        ("entities", {}),
        ("token_mentions", None),
        ("token_mentions", {}),
        ("fact_candidates", None),
        ("fact_candidates", {}),
        ("exact_duplicate_candidates", None),
        ("exact_duplicate_candidates", {}),
        ("story_candidates", None),
        ("story_candidates", {}),
    ],
)
def test_agent_admission_context_loader_rejects_malformed_evidence_arrays_without_json_list_defaults(
    field_name: str,
    bad_value: object,
) -> None:
    row = _valid_agent_admission_context_loader_row()
    row[field_name] = bad_value
    conn = NewsPageRowsConnection(rows=[row])
    repo = NewsItemRepository(conn)

    with pytest.raises(ValueError, match=f"news_agent_admission_context.*{field_name}"):
        repo.load_agent_admission_contexts(news_item_ids=["news-1"], now_ms=1_000)


def test_agent_similar_story_context_requires_story_identity_version_without_default() -> None:
    conn = CapturingConnection()
    repo = NewsItemRepository(conn)

    with pytest.raises(ValueError, match="news_agent_admission_story_identity_version_required"):
        repo._agent_similar_story_context({"news_item_id": "news-1", "story_key": "story:news-1"})

    assert conn.statements == []


def test_news_page_row_payload_hash_rejects_legacy_story_keys_before_write() -> None:
    conn = CapturingConnection()
    repo = NewsPageRepository(conn)
    row = _valid_news_page_row()
    row["story"] = {123: "legacy"}

    with pytest.raises(ValueError, match="current payload hash payload has non-string keys"):
        repo.replace_page_rows_for_items(news_item_ids=[], rows=[row])

    assert conn.events == []
    assert not any("INSERT INTO news_page_rows" in sql for sql, _params in conn.statements)
    assert conn.params is None or "INSERT INTO news_page_rows" not in conn.sql


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [
        ("token_lanes", None),
        ("fact_lanes", None),
        ("story", None),
        ("token_impacts", None),
        ("content_tags", None),
        ("content_classification", None),
        ("source", None),
        ("signal", None),
        ("provider_rating", None),
        ("agent_brief", None),
        ("market_scope", None),
        ("macro_event_flow", None),
        ("agent_admission", None),
        ("token_lanes", {}),
        ("story", []),
        ("source", []),
        ("macro_event_flow", []),
        ("macro_event_flow", {"window": "recent"}),
    ],
)
def test_news_page_row_payload_requires_formal_json_sections_before_write(field_name: str, bad_value: object) -> None:
    conn = CapturingConnection()
    repo = NewsPageRepository(conn)
    row = _valid_news_page_row()
    if bad_value is None:
        row.pop(field_name)
    else:
        row[field_name] = bad_value

    with pytest.raises(ValueError, match=f"news_page_row_payload.*{field_name}"):
        repo.replace_page_rows_for_items(news_item_ids=[], rows=[row])

    assert conn.events == []
    assert not any("INSERT INTO news_page_rows" in sql for sql, _params in conn.statements)


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [
        ("representative_news_item_id", None),
        ("representative_news_item_id", ""),
        ("story_key", None),
        ("story_key", ""),
        ("content_class", None),
        ("content_class", ""),
        ("agent_status", None),
        ("agent_status", ""),
        ("agent_admission_status", None),
        ("agent_admission_status", ""),
        ("agent_admission_reason", None),
        ("agent_admission_reason", ""),
        ("agent_representative_news_item_id", None),
        ("agent_representative_news_item_id", ""),
    ],
)
def test_news_page_row_payload_requires_formal_text_identity_before_write(
    field_name: str,
    bad_value: object,
) -> None:
    conn = CapturingConnection()
    repo = NewsPageRepository(conn)
    row = _valid_news_page_row()
    if bad_value is None:
        row.pop(field_name)
    else:
        row[field_name] = bad_value

    with pytest.raises(ValueError, match=f"news_page_row_payload.*{field_name}"):
        repo.replace_page_rows_for_items(news_item_ids=[], rows=[row])

    assert conn.events == []
    assert not any("INSERT INTO news_page_rows" in sql for sql, _params in conn.statements)


def test_news_page_row_payload_requires_formal_agent_brief_status_before_write() -> None:
    conn = CapturingConnection()
    repo = NewsPageRepository(conn)
    row = _valid_news_page_row()
    agent_brief = dict(row["agent_brief"])
    agent_brief.pop("status")
    row["agent_brief"] = agent_brief

    with pytest.raises(ValueError, match=r"news_page_row_payload.*agent_brief.*status"):
        repo.replace_page_rows_for_items(news_item_ids=[], rows=[row])

    assert conn.events == []
    assert not any("INSERT INTO news_page_rows" in sql for sql, _params in conn.statements)


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [
        ("direction", None),
        ("direction", ""),
        ("decision_class", None),
        ("decision_class", ""),
    ],
)
def test_news_page_row_payload_ready_agent_brief_requires_formal_signal_fields_before_write(
    field_name: str,
    bad_value: object,
) -> None:
    conn = CapturingConnection()
    repo = NewsPageRepository(conn)
    row = _valid_news_page_row()
    agent_brief = {
        "status": "ready",
        "direction": "bullish",
        "decision_class": "driver",
        "summary_zh": "当前摘要",
    }
    if bad_value is None:
        agent_brief.pop(field_name)
    else:
        agent_brief[field_name] = bad_value
    row["agent_brief"] = agent_brief
    row["agent_status"] = "ready"

    with pytest.raises(ValueError, match=rf"news_page_row_payload.*agent_brief.*{field_name}"):
        repo.replace_page_rows_for_items(news_item_ids=[], rows=[row])

    assert conn.events == []
    assert not any("INSERT INTO news_page_rows" in sql for sql, _params in conn.statements)


def test_news_page_row_payload_rejects_agent_status_mismatch_before_write() -> None:
    conn = CapturingConnection()
    repo = NewsPageRepository(conn)
    row = _valid_news_page_row()
    row["agent_status"] = "ready"

    with pytest.raises(ValueError, match=r"news_page_row_payload.*agent_status.*mismatch"):
        repo.replace_page_rows_for_items(news_item_ids=[], rows=[row])

    assert conn.events == []
    assert not any("INSERT INTO news_page_rows" in sql for sql, _params in conn.statements)


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [
        ("canonical_item_key", None),
        ("canonical_item_key", ""),
        ("duplicate_count", None),
        ("duplicate_count", "2"),
        ("duplicate_count", 2.5),
        ("duplicate_count", -1),
        ("source_ids_json", None),
        ("source_ids_json", {}),
        ("source_domains_json", None),
        ("source_domains_json", {}),
        ("provider_article_keys_json", None),
        ("provider_article_keys_json", {}),
    ],
)
def test_news_page_row_payload_requires_formal_summary_fields_before_write(
    field_name: str,
    bad_value: object,
) -> None:
    conn = CapturingConnection()
    repo = NewsPageRepository(conn)
    row = _valid_news_page_row()
    if bad_value is None:
        row.pop(field_name)
    else:
        row[field_name] = bad_value

    with pytest.raises(ValueError, match=f"news_page_row_payload.*{field_name}"):
        repo.replace_page_rows_for_items(news_item_ids=[], rows=[row])

    assert conn.events == []
    assert not any("INSERT INTO news_page_rows" in sql for sql, _params in conn.statements)


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [
        ("headline", None),
        ("headline", 123),
        ("summary", None),
        ("summary", 123),
        ("source_domain", None),
        ("source_domain", 123),
        ("canonical_url", None),
        ("canonical_url", 123),
    ],
)
def test_news_page_row_payload_requires_formal_display_strings_before_write(
    field_name: str,
    bad_value: object,
) -> None:
    conn = CapturingConnection()
    repo = NewsPageRepository(conn)
    row = _valid_news_page_row()
    if bad_value is None:
        row.pop(field_name)
    else:
        row[field_name] = bad_value

    with pytest.raises(ValueError, match=f"news_page_row_payload.*{field_name}"):
        repo.replace_page_rows_for_items(news_item_ids=[], rows=[row])

    assert conn.events == []
    assert not any("INSERT INTO news_page_rows" in sql for sql, _params in conn.statements)


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [
        ("latest_at_ms", True),
        ("latest_at_ms", "1779000000000"),
        ("latest_at_ms", 1_779_000_000_000.5),
        ("latest_at_ms", 0),
        ("computed_at_ms", True),
        ("computed_at_ms", "1779000000000"),
        ("computed_at_ms", 1_779_000_000_000.5),
        ("computed_at_ms", 0),
        ("agent_brief_computed_at_ms", True),
        ("agent_brief_computed_at_ms", "1779000000000"),
        ("agent_brief_computed_at_ms", 1_779_000_000_000.5),
        ("agent_brief_computed_at_ms", 0),
    ],
)
def test_news_page_row_payload_requires_typed_timing_fields_before_write(
    field_name: str,
    bad_value: object,
) -> None:
    conn = CapturingConnection()
    repo = NewsPageRepository(conn)
    row = _valid_news_page_row()
    row[field_name] = bad_value

    with pytest.raises(ValueError, match=f"news_page_row_payload.*{field_name}"):
        repo.replace_page_rows_for_items(news_item_ids=[], rows=[row])

    assert conn.events == []
    assert not any("INSERT INTO news_page_rows" in sql for sql, _params in conn.statements)


@pytest.mark.parametrize("field_name", ["status", "reason", "representative_news_item_id", "basis", "version"])
def test_news_page_row_payload_requires_formal_agent_admission_fields_before_write(field_name: str) -> None:
    conn = CapturingConnection()
    repo = NewsPageRepository(conn)
    row = _valid_news_page_row()
    agent_admission = dict(row["agent_admission"])
    agent_admission.pop(field_name)
    row["agent_admission"] = agent_admission

    with pytest.raises(ValueError, match=f"news_page_row_payload.*agent_admission.*{field_name}"):
        repo.replace_page_rows_for_items(news_item_ids=[], rows=[row])

    assert conn.events == []
    assert not any("INSERT INTO news_page_rows" in sql for sql, _params in conn.statements)


@pytest.mark.parametrize(
    ("top_level_field", "admission_field"),
    [
        ("agent_admission_status", "status"),
        ("agent_admission_reason", "reason"),
        ("agent_representative_news_item_id", "representative_news_item_id"),
    ],
)
def test_news_page_row_payload_rejects_agent_admission_mismatch_before_write(
    top_level_field: str,
    admission_field: str,
) -> None:
    conn = CapturingConnection()
    repo = NewsPageRepository(conn)
    row = _valid_news_page_row()
    agent_admission = dict(row["agent_admission"])
    agent_admission[admission_field] = "different"
    row["agent_admission"] = agent_admission

    with pytest.raises(ValueError, match=f"news_page_row_payload.*{top_level_field}.*mismatch"):
        repo.replace_page_rows_for_items(news_item_ids=[], rows=[row])

    assert conn.events == []
    assert not any("INSERT INTO news_page_rows" in sql for sql, _params in conn.statements)


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [
        ("representative_news_item_id", None),
        ("story_key", None),
        ("story", None),
        ("market_scope", None),
        ("agent_admission_status", None),
        ("agent_admission_reason", None),
        ("agent_admission", None),
        ("agent_representative_news_item_id", None),
        ("content_class", None),
        ("content_tags", None),
        ("content_classification", None),
        ("signal", None),
        ("provider_rating", None),
        ("token_impacts", None),
        ("token_lanes", None),
        ("fact_lanes", None),
        ("story", []),
        ("signal", []),
        ("token_lanes", {}),
        ("content_class", {}),
    ],
)
def test_news_item_detail_requires_formal_page_row_projection_without_raw_item_fallback(
    field_name: str, bad_value: object
) -> None:
    page_row = _valid_news_item_detail_page_row()
    if bad_value is None:
        page_row.pop(field_name)
    else:
        page_row[field_name] = bad_value
    conn = NewsItemDetailConnection(page_row=page_row)
    repo = NewsPageRepository(conn)

    with pytest.raises(ValueError, match=f"news_item_detail_projection.*{field_name}"):
        repo.get_news_item_detail(news_item_id="news-1")


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [
        ("entities", None),
        ("entities", {}),
        ("token_mentions", None),
        ("token_mentions", {}),
        ("fact_candidates", None),
        ("fact_candidates", {}),
    ],
)
def test_news_item_detail_requires_explicit_evidence_arrays_without_json_list_defaults(
    field_name: str,
    bad_value: object,
) -> None:
    base_row = _valid_news_item_detail_base_row()
    base_row[field_name] = bad_value
    conn = NewsItemDetailConnection(
        page_row=_valid_news_item_detail_page_row(),
        base_row=base_row,
    )
    repo = NewsPageRepository(conn)

    with pytest.raises(ValueError, match=f"news_item_detail_evidence.*{field_name}"):
        repo.get_news_item_detail(news_item_id="news-1")


def test_news_item_detail_reads_agent_current_from_projected_page_row_only() -> None:
    page_row = _valid_news_item_detail_page_row()
    page_row["page_agent_brief"] = {
        "status": "ready",
        "direction": "bullish",
        "decision_class": "driver",
        "summary_zh": "Projected story current.",
    }
    conn = NewsItemDetailConnection(page_row=page_row)
    repo = NewsPageRepository(conn)

    detail = repo.get_news_item_detail(news_item_id="news-1")

    assert detail is not None
    assert detail["agent_brief"] == {
        "status": "ready",
        "direction": "bullish",
        "decision_class": "driver",
        "summary_zh": "Projected story current.",
    }
    assert "agent_run" not in detail
    combined_sql = "\n".join(sql for sql, _params in conn.statements)
    assert "news_item_agent_briefs" not in combined_sql
    assert "news_item_agent_runs" not in combined_sql


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [
        ("representative_news_item_id", None),
        ("story_key", None),
        ("story", None),
        ("source_ids", None),
        ("source_domains", None),
        ("token_lanes", None),
        ("fact_lanes", None),
        ("signal", None),
        ("provider_rating", None),
        ("token_impacts", None),
        ("content_class", None),
        ("content_tags", None),
        ("content_classification", None),
        ("source", None),
        ("agent_brief", None),
        ("market_scope", None),
        ("agent_admission_status", None),
        ("agent_admission_reason", None),
        ("agent_admission", None),
        ("agent_representative_news_item_id", None),
        ("story", []),
        ("agent_brief", []),
        ("token_lanes", {}),
        ("content_class", {}),
    ],
)
def test_list_news_page_rows_requires_formal_projected_sections_without_public_defaults(
    field_name: str, bad_value: object
) -> None:
    page_row = _valid_news_page_read_row()
    if bad_value is None:
        page_row.pop(field_name)
    else:
        page_row[field_name] = bad_value
    conn = NewsPageRowsConnection(rows=[page_row])
    repo = NewsPageRepository(conn)

    with pytest.raises(ValueError, match=f"news_page_row_projection.*{field_name}"):
        repo.list_news_page_rows(limit=1)


@pytest.mark.parametrize("limit", [-1, True, "1"])
def test_list_news_page_rows_rejects_malformed_limit_before_sql(limit: object) -> None:
    conn = NewsPageRowsConnection(rows=[])
    repo = NewsPageRepository(conn)

    with pytest.raises(ValueError, match="news_page_rows_limit_required"):
        repo.list_news_page_rows(limit=limit)  # type: ignore[arg-type]

    assert conn.statements == []


def test_list_news_page_rows_omits_blank_optional_text_from_failed_agent_brief() -> None:
    page_row = _valid_news_page_read_row()
    page_row["agent_status"] = "failed"
    page_row["agent_brief"] = {
        "status": "failed",
        "direction": "neutral",
        "decision_class": "discard",
        "title_zh": "",
        "summary_zh": "",
        "market_read_zh": "",
        "event_type": "",
        "bull_strength": "absent",
        "bear_strength": "absent",
        "computed_at_ms": 1_779_000_000_600,
        "data_gap_count": 1,
        "market_impacts": [],
        "bull_view": {"strength": "absent", "thesis_zh": "", "evidence_refs": []},
        "bear_view": {"strength": "absent", "thesis_zh": "", "evidence_refs": []},
    }
    conn = NewsPageRowsConnection(rows=[page_row])
    repo = NewsPageRepository(conn)

    rows = repo.list_news_page_rows(limit=1)

    agent_brief = rows[0]["agent_brief"]
    assert agent_brief["status"] == "failed"
    assert agent_brief["direction"] == "neutral"
    assert agent_brief["decision_class"] == "discard"
    assert agent_brief["bull_strength"] == "absent"
    assert agent_brief["bear_strength"] == "absent"
    assert agent_brief["computed_at_ms"] == 1_779_000_000_600
    assert agent_brief["data_gap_count"] == 1
    assert "title_zh" not in agent_brief
    assert "summary_zh" not in agent_brief
    assert "market_read_zh" not in agent_brief
    assert "event_type" not in agent_brief


def test_list_news_page_rows_filters_and_requires_macro_event_flow_when_requested() -> None:
    page_row = _valid_news_page_read_row()
    page_row["macro_event_flow"] = {
        "window": "recent",
        "window_label": "近期",
        "severity": "high",
        "severity_label": "高",
        "category": "macro_policy",
        "category_label": "美联储",
        "impact": "mainline_driver",
        "impact_label": "改变主线",
        "watch": "SPX · 美联储",
    }
    conn = NewsPageRowsConnection(rows=[page_row])
    repo = NewsPageRepository(conn)

    rows = repo.list_news_page_rows(limit=1, macro_event_flow=True)

    assert rows[0]["macro_event_flow"] == page_row["macro_event_flow"]
    assert "macro_event_flow_json AS macro_event_flow" in conn.sql
    assert "macro_event_flow_json IS NOT NULL" in conn.sql


def test_list_news_page_rows_rejects_macro_event_flow_rows_without_projection_contract() -> None:
    page_row = _valid_news_page_read_row()
    conn = NewsPageRowsConnection(rows=[page_row])
    repo = NewsPageRepository(conn)

    with pytest.raises(ValueError, match=r"news_page_row_projection.*macro_event_flow"):
        repo.list_news_page_rows(limit=1, macro_event_flow=True)


def test_high_signal_notification_candidates_are_narrow_typed_and_sql_recent() -> None:
    conn = NewsPageRowsConnection(
        rows=[
            {
                "row_id": "row-1",
                "news_item_id": "news-1",
                "representative_news_item_id": "news-1",
                "story_key": "story-1",
                "latest_at_ms": 1_700_000_000_000,
                "headline": "Headline",
                "source_domain": "example.test",
                "canonical_url": "https://example.test/news-1",
                "direction": "bullish",
                "decision_class": "driver",
                "title_zh": "标题",
                "projected_title_zh": "投影标题",
                "summary_zh": "摘要",
                "affected_entities": [{"symbol": "BTC"}],
                "token_impacts": [{"symbol": "ETH"}],
                "external_push_ready": True,
                "external_push_basis": "agent_brief",
                "external_push_block_reason": None,
            }
        ]
    )
    repo = NewsPageRepository(conn)

    candidates = repo.list_news_high_signal_notification_candidates(limit=1, since_ms=1_699_999_000_000)

    assert candidates[0].affected_symbols == ("BTC",)
    assert conn.params == (NEWS_PAGE_PROJECTION_VERSION, 1_699_999_000_000, 1)
    assert "latest_at_ms >= %s" in conn.sql
    assert "agent_brief_json ->> 'direction' AS direction" in conn.sql
    assert "story_json" not in conn.sql
    assert "market_scope_json" not in conn.sql
    assert "duplicate_count" not in conn.sql


@pytest.mark.parametrize("limit", [-1, True, "1"])
def test_high_signal_notification_candidates_reject_malformed_limit_before_sql(limit: object) -> None:
    conn = NewsPageRowsConnection(rows=[])
    repo = NewsPageRepository(conn)

    with pytest.raises(ValueError, match="news_high_signal_notification_limit_required"):
        repo.list_news_high_signal_notification_candidates(limit=limit, since_ms=1)  # type: ignore[arg-type]

    assert conn.statements == []


@pytest.mark.parametrize("since_ms", [-1, True, "1"])
def test_high_signal_notification_candidates_reject_malformed_since_ms_before_sql(since_ms: object) -> None:
    conn = NewsPageRowsConnection(rows=[])
    repo = NewsPageRepository(conn)

    with pytest.raises(ValueError, match="news_high_signal_notification_since_ms_required"):
        repo.list_news_high_signal_notification_candidates(limit=1, since_ms=since_ms)  # type: ignore[arg-type]

    assert conn.statements == []


def test_unprocessed_item_loader_selects_provider_article_keys_for_story_identity() -> None:
    conn = ClaimUnprocessedItemsConnection(rows=[], rowcount=0)
    repo = NewsItemRepository(conn)

    rows = repo.claim_unprocessed_items(
        limit=10,
        lease_owner="worker",
        lease_ms=120_000,
        now_ms=1_000,
    )

    assert rows == []
    assert "claimed.provider_article_keys_json" in conn.claim_sql
    assert "sources.provider_type" in conn.claim_sql


def test_claim_unprocessed_items_returning_rows_require_cursor_rowcount() -> None:
    conn = ClaimUnprocessedItemsConnection(
        rows=[{"news_item_id": "news-1", "processing_attempts": 1}],
        omit_rowcount=True,
    )
    repo = NewsItemRepository(conn)

    with pytest.raises(TypeError, match="news_repository_rowcount_invalid"):
        repo.claim_unprocessed_items(
            limit=1,
            lease_owner="worker",
            lease_ms=120_000,
            now_ms=1_000,
        )

    assert "UPDATE news_items AS items" in conn.claim_sql
    assert "RETURNING items.*" in conn.claim_sql


@pytest.mark.parametrize("rowcount", [True, False, "1", None, -1, 0, 2])
def test_claim_unprocessed_items_returning_rows_reject_invalid_or_mismatched_rowcount(
    rowcount: object,
) -> None:
    conn = ClaimUnprocessedItemsConnection(
        rows=[{"news_item_id": "news-1", "processing_attempts": 1}],
        rowcount=rowcount,
    )
    repo = NewsItemRepository(conn)

    with pytest.raises(TypeError, match="news_repository_rowcount_invalid"):
        repo.claim_unprocessed_items(
            limit=1,
            lease_owner="worker",
            lease_ms=120_000,
            now_ms=1_000,
        )

    assert "RETURNING items.*" in conn.claim_sql


def test_claim_unprocessed_items_returning_rows_accept_zero_row_noop() -> None:
    conn = ClaimUnprocessedItemsConnection(rows=[], rowcount=0)
    repo = NewsItemRepository(conn)

    rows = repo.claim_unprocessed_items(
        limit=1,
        lease_owner="worker",
        lease_ms=120_000,
        now_ms=1_000,
    )

    assert rows == []
    assert conn.params == (1_000, 1, "worker", 121_000, 1_000)


def test_claim_unprocessed_items_returning_rows_accept_matching_claim_rows() -> None:
    conn = ClaimUnprocessedItemsConnection(
        rows=[{"news_item_id": "news-1", "processing_attempts": 1}],
        rowcount=1,
    )
    repo = NewsItemRepository(conn)

    rows = repo.claim_unprocessed_items(
        limit=1,
        lease_owner="worker",
        lease_ms=120_000,
        now_ms=1_000,
    )

    assert rows == [{"news_item_id": "news-1", "processing_attempts": 1}]
    assert conn.params == (1_000, 1, "worker", 121_000, 1_000)


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        pytest.param({"limit": -1}, "news_item_claim_limit_required", id="negative-limit"),
        pytest.param({"limit": True}, "news_item_claim_limit_required", id="bool-limit"),
        pytest.param({"limit": "1"}, "news_item_claim_limit_required", id="string-limit"),
        pytest.param({"lease_ms": 0}, "news_item_claim_lease_ms_required", id="zero-lease"),
        pytest.param({"lease_ms": True}, "news_item_claim_lease_ms_required", id="bool-lease"),
        pytest.param({"lease_ms": "60000"}, "news_item_claim_lease_ms_required", id="string-lease"),
    ],
)
def test_claim_unprocessed_items_rejects_malformed_parameters_before_sql(
    overrides: dict[str, object],
    error: str,
) -> None:
    conn = ClaimUnprocessedItemsConnection(rows=[], rowcount=0)
    repo = NewsItemRepository(conn)
    params: dict[str, object] = {
        "limit": 1,
        "lease_owner": "worker",
        "lease_ms": 120_000,
        "now_ms": 1_000,
    }
    params.update(overrides)

    with pytest.raises(ValueError, match=error):
        repo.claim_unprocessed_items(**params)

    assert conn.statements == []


def test_update_item_market_scope_and_story_identity_rejects_unsupported_payload_shape() -> None:
    conn = CapturingConnection()
    repo = NewsItemRepository(conn)

    try:
        repo.update_item_market_scope_and_story_identity(
            news_item_id="news-1",
            market_scope=object(),
            story_identity=_valid_story_identity(),
            now_ms=1_000,
        )
    except ValueError as exc:
        assert "market scope payload" in str(exc)
    else:
        raise AssertionError("expected unsupported market scope payload shape to raise")

    assert conn.statements == []


def test_update_item_market_scope_and_story_identity_rejects_unsupported_story_identity_shape() -> None:
    conn = CapturingConnection()
    repo = NewsItemRepository(conn)

    with pytest.raises(ValueError, match="story identity payload"):
        repo.update_item_market_scope_and_story_identity(
            news_item_id="news-1",
            market_scope=_valid_market_scope(),
            story_identity=object(),
            now_ms=1_000,
        )

    assert conn.statements == []


def test_update_item_market_scope_and_story_identity_requires_formal_current_objects_without_mapping_fallback() -> None:
    conn = CapturingConnection()
    repo = NewsItemRepository(conn)

    with pytest.raises(ValueError, match="market scope payload"):
        repo.update_item_market_scope_and_story_identity(
            news_item_id="news-1",
            market_scope=_valid_market_scope_payload(),
            story_identity=_valid_story_identity(),
            now_ms=1_000,
        )

    with pytest.raises(ValueError, match="story identity payload"):
        repo.update_item_market_scope_and_story_identity(
            news_item_id="news-1",
            market_scope=_valid_market_scope(),
            story_identity=_valid_story_identity_payload(),
            now_ms=1_000,
        )

    assert conn.statements == []


def test_update_item_agent_admission_requires_formal_admission_without_alias_or_default_fallback() -> None:
    conn = CapturingConnection()
    repo = NewsItemRepository(conn)

    with pytest.raises(ValueError, match="agent admission payload"):
        repo.update_item_agent_admission(
            news_item_id="news-1",
            admission={
                "status": "eligible",
                "reason": "eligible",
                "agent_representative_news_item_id": "news-1",
                "basis": {"market_scope": ["crypto"]},
            },
            now_ms=1_000,
        )

    with pytest.raises(ValueError, match="agent admission payload"):
        repo.update_item_market_scope_and_agent_admission(
            news_item_id="news-1",
            market_scope=_valid_market_scope(),
            story_identity=_valid_story_identity(),
            admission=_valid_agent_admission_payload(),
            now_ms=1_000,
        )

    assert conn.statements == []


def test_news_repository_write_counts_require_cursor_rowcount() -> None:
    conn = RowcountConnection(omit_rowcount=True)
    repo = NewsItemRepository(conn)

    with pytest.raises(TypeError, match="news_repository_rowcount_invalid"):
        repo.mark_news_items_for_reprocessing(news_item_ids=["news-1"], now_ms=1_000)


@pytest.mark.parametrize("rowcount", ["bad", True, -1])
def test_news_repository_write_counts_reject_invalid_cursor_rowcount(rowcount: object) -> None:
    conn = RowcountConnection(rowcount=rowcount)
    repo = NewsItemRepository(conn)

    with pytest.raises(TypeError, match="news_repository_rowcount_invalid"):
        repo.mark_news_items_for_reprocessing(news_item_ids=["news-1"], now_ms=1_000)


def test_upsert_source_returning_row_requires_cursor_rowcount() -> None:
    conn = UpsertSourceConnection(
        existing=None,
        row={"source_id": "source-1", "provider_type": "rss"},
        omit_rowcount=True,
    )
    repo = NewsSourceRepository(conn)

    with pytest.raises(TypeError, match="news_repository_rowcount_invalid"):
        _upsert_source(repo)

    assert len(conn.statements) == 2
    assert "INSERT INTO news_sources" in conn.statements[1][0]


@pytest.mark.parametrize("rowcount", [True, False, "1", None, -1, 0, 2])
def test_upsert_source_returning_row_rejects_invalid_or_mismatched_rowcount(rowcount: object) -> None:
    conn = UpsertSourceConnection(
        existing=None,
        row={"source_id": "source-1", "provider_type": "rss"},
        rowcount=rowcount,
    )
    repo = NewsSourceRepository(conn)

    with pytest.raises(TypeError, match="news_repository_rowcount_invalid"):
        _upsert_source(repo)

    assert len(conn.statements) == 2
    assert "INSERT INTO news_sources" in conn.statements[1][0]


def test_upsert_source_returning_row_rejects_missing_required_row() -> None:
    conn = UpsertSourceConnection(existing=None, row=None, rowcount=1)
    repo = NewsSourceRepository(conn)

    with pytest.raises(TypeError, match="news_repository_rowcount_invalid"):
        _upsert_source(repo)

    assert len(conn.statements) == 2
    assert "INSERT INTO news_sources" in conn.statements[1][0]


def test_upsert_source_returning_row_accepts_matching_required_row() -> None:
    conn = UpsertSourceConnection(
        existing=None,
        row={"source_id": "source-1", "provider_type": "rss"},
        rowcount=1,
    )
    repo = NewsSourceRepository(conn)

    row = _upsert_source(repo)

    assert row["source_id"] == "source-1"
    assert row["status"] == "inserted"
    assert len(conn.statements) == 2
    assert "INSERT INTO news_sources" in conn.statements[1][0]


def test_news_source_config_payload_hash_is_stable_and_changes_with_config() -> None:
    source = {
        "source_id": "source-1",
        "provider_type": "rss",
        "feed_url": "https://example.com/feed.xml",
        "source_domain": "example.com",
        "source_name": "Example",
        "authority_scope": {"markets": ["crypto"], "region": "global"},
    }

    first = news_source_config_payload_hash(source)
    reordered = news_source_config_payload_hash(
        {**source, "authority_scope": {"region": "global", "markets": ["crypto"]}}
    )
    changed = news_source_config_payload_hash({**source, "refresh_interval_seconds": 301})

    assert first == reordered
    assert first.startswith("sha256:")
    assert len(first) == 71
    assert changed != first


def test_upsert_source_preserves_terminal_disable_for_same_hash_and_clears_it_for_changed_hash() -> None:
    source = {
        "source_id": "source-1",
        "provider_type": "rss",
        "feed_url": "https://example.com/feed.xml",
        "source_domain": "example.com",
        "source_name": "Example",
    }
    terminal_hash = news_source_config_payload_hash(source)
    existing = {
        "source_id": "source-1",
        "provider_type": "rss",
        "feed_url": "https://example.com/feed.xml",
        "source_domain": "example.com",
        "source_name": "Example",
        "source_role": "observed_source",
        "trust_tier": "standard",
        "managed_by_config": True,
        "enabled": False,
        "refresh_interval_seconds": 300,
        "coverage_tags_json": [],
        "asset_universe_json": [],
        "authority_scope_json": {},
        "fetch_policy_json": {},
        "cost_policy_json": {},
        "config_payload_hash": terminal_hash,
        "terminal_config_payload_hash": terminal_hash,
    }
    changed_hash = news_source_config_payload_hash({**source, "refresh_interval_seconds": 301})
    conn = UpsertSourceConnection(
        existing=existing,
        row={**existing, "config_payload_hash": changed_hash, "terminal_config_payload_hash": None},
    )
    repo = NewsSourceRepository(conn)

    row = repo.upsert_source(**source, refresh_interval_seconds=301, now_ms=2_000)

    sql, params = conn.statements[1]
    assert row["status"] == "updated"
    assert "news_sources.terminal_config_payload_hash = EXCLUDED.config_payload_hash" in sql
    assert "news_sources.terminal_config_payload_hash IS DISTINCT FROM EXCLUDED.config_payload_hash" in sql
    assert changed_hash in params


def test_disable_source_persists_terminal_hash_from_current_config() -> None:
    config_hash = news_source_config_payload_hash(
        {
            "source_id": "source-1",
            "provider_type": "rss",
            "feed_url": "https://example.com/feed.xml",
            "source_domain": "example.com",
            "source_name": "Example",
        }
    )
    conn = SingleReturningConnection(
        row={
            "source_id": "source-1",
            "enabled": False,
            "config_payload_hash": config_hash,
            "terminal_config_payload_hash": config_hash,
        }
    )
    repo = NewsSourceRepository(conn)

    row = repo.disable_source(
        source_id="source-1",
        error="news_provider_http_402",
        now_ms=2_000,
    )

    assert row["terminal_config_payload_hash"] == config_hash
    assert "terminal_config_payload_hash = config_payload_hash" in conn.statements[0][0]


@pytest.mark.parametrize(
    ("field_name", "bad_value", "error"),
    [
        ("authority_scope", "authority", "news_source_authority_scope_required"),
        ("fetch_policy", ["rest_limit"], "news_source_fetch_policy_required"),
        ("cost_policy", "free", "news_source_cost_policy_required"),
    ],
)
def test_upsert_source_rejects_malformed_policy_mappings_before_sql(
    field_name: str,
    bad_value: object,
    error: str,
) -> None:
    conn = UpsertSourceConnection(
        existing=None,
        row={"source_id": "source-1", "provider_type": "rss"},
    )
    repo = NewsSourceRepository(conn)

    kwargs = {field_name: bad_value}
    with pytest.raises(ValueError, match=error):
        repo.upsert_source(
            source_id="source-1",
            provider_type="rss",
            feed_url="https://example.com/feed.xml",
            source_domain="example.com",
            source_name="Example",
            now_ms=1_000,
            **kwargs,
        )

    assert conn.statements == []


def test_upsert_provider_item_returning_row_requires_cursor_rowcount() -> None:
    conn = UpsertProviderItemConnection(
        existing=None,
        row={"provider_item_id": "provider-item-1"},
        omit_rowcount=True,
    )
    repo = NewsSourceRepository(conn)

    with pytest.raises(TypeError, match="news_repository_rowcount_invalid"):
        _upsert_provider_item(repo)

    assert len(conn.statements) == 3
    assert "INSERT INTO news_provider_items" in conn.statements[2][0]


@pytest.mark.parametrize("rowcount", [True, False, "1", None, -1, 0, 2])
def test_upsert_provider_item_returning_row_rejects_invalid_or_mismatched_rowcount(
    rowcount: object,
) -> None:
    conn = UpsertProviderItemConnection(
        existing=None,
        row={"provider_item_id": "provider-item-1"},
        rowcount=rowcount,
    )
    repo = NewsSourceRepository(conn)

    with pytest.raises(TypeError, match="news_repository_rowcount_invalid"):
        _upsert_provider_item(repo)

    assert len(conn.statements) == 3
    assert "INSERT INTO news_provider_items" in conn.statements[2][0]


def test_upsert_provider_item_returning_row_rejects_missing_required_row() -> None:
    conn = UpsertProviderItemConnection(existing=None, row=None, rowcount=1)
    repo = NewsSourceRepository(conn)

    with pytest.raises(TypeError, match="news_repository_rowcount_invalid"):
        _upsert_provider_item(repo)

    assert len(conn.statements) == 3
    assert "INSERT INTO news_provider_items" in conn.statements[2][0]


def test_upsert_provider_item_returning_row_accepts_matching_required_row() -> None:
    conn = UpsertProviderItemConnection(
        existing=None,
        row={"provider_item_id": "provider-item-1", "source_id": "source-1"},
        rowcount=1,
    )
    repo = NewsSourceRepository(conn)

    row = _upsert_provider_item(repo)

    assert row["provider_item_id"] == "provider-item-1"
    assert row["status"] == "inserted"
    assert row["incoming_provider_payload_status"] == "ready"
    assert len(conn.statements) == 3
    assert "INSERT INTO news_provider_items" in conn.statements[2][0]


def test_upsert_canonical_news_item_returning_row_requires_cursor_rowcount() -> None:
    conn = UpsertCanonicalNewsItemConnection(
        row={"news_item_id": "news-1"},
        omit_rowcount=True,
    )
    repo = NewsItemRepository(conn)

    with pytest.raises(TypeError, match="news_repository_rowcount_invalid"):
        _upsert_canonical_news_item(repo)

    assert "INSERT INTO news_items" in conn.insert_news_items_sql


@pytest.mark.parametrize("rowcount", [True, False, "1", None, -1, 0, 2])
def test_upsert_canonical_news_item_returning_row_rejects_invalid_or_mismatched_rowcount(
    rowcount: object,
) -> None:
    conn = UpsertCanonicalNewsItemConnection(
        row={"news_item_id": "news-1"},
        rowcount=rowcount,
    )
    repo = NewsItemRepository(conn)

    with pytest.raises(TypeError, match="news_repository_rowcount_invalid"):
        _upsert_canonical_news_item(repo)

    assert "INSERT INTO news_items" in conn.insert_news_items_sql


def test_upsert_canonical_news_item_returning_row_rejects_missing_required_row() -> None:
    conn = UpsertCanonicalNewsItemConnection(row=None, rowcount=1)
    repo = NewsItemRepository(conn)

    with pytest.raises(TypeError, match="news_repository_rowcount_invalid"):
        _upsert_canonical_news_item(repo)

    assert "INSERT INTO news_items" in conn.insert_news_items_sql


def test_upsert_canonical_news_item_returning_row_accepts_matching_required_row() -> None:
    conn = UpsertCanonicalNewsItemConnection(
        row={"news_item_id": "news-1", "canonical_item_key": "url:https://example.com/news/1"},
        rowcount=1,
    )
    repo = NewsItemRepository(conn)

    row = _upsert_canonical_news_item(repo)

    assert row["news_item_id"] == "news-1"
    assert row["status"] == "inserted"
    assert row["affected_news_item_ids"] == ["news-1"]
    assert "INSERT INTO news_items" in conn.insert_news_items_sql


def test_upsert_canonical_news_item_observation_edge_requires_cursor_rowcount() -> None:
    conn = UpsertCanonicalNewsItemConnection(
        row={"news_item_id": "news-1", "canonical_item_key": "url:https://example.com/news/1"},
        edge_omit_rowcount=True,
    )
    repo = NewsItemRepository(conn)

    with pytest.raises(TypeError, match="news_repository_rowcount_invalid"):
        _upsert_canonical_news_item(repo)

    assert "INSERT INTO news_item_observation_edges" in conn.insert_observation_edge_sql


@pytest.mark.parametrize("rowcount", [True, False, "1", None, -1, 0, 2])
def test_upsert_canonical_news_item_observation_edge_rejects_invalid_rowcount(
    rowcount: object,
) -> None:
    conn = UpsertCanonicalNewsItemConnection(
        row={"news_item_id": "news-1", "canonical_item_key": "url:https://example.com/news/1"},
        edge_rowcount=rowcount,
    )
    repo = NewsItemRepository(conn)

    with pytest.raises(TypeError, match="news_repository_rowcount_invalid"):
        _upsert_canonical_news_item(repo)

    assert "INSERT INTO news_item_observation_edges" in conn.insert_observation_edge_sql


def test_upsert_canonical_news_item_observation_edge_accepts_required_rowcount() -> None:
    conn = UpsertCanonicalNewsItemConnection(
        row={"news_item_id": "news-1", "canonical_item_key": "url:https://example.com/news/1"},
        edge_rowcount=1,
    )
    repo = NewsItemRepository(conn)

    row = _upsert_canonical_news_item(repo)

    assert row["news_item_id"] == "news-1"
    assert row["status"] == "inserted"
    assert "INSERT INTO news_item_observation_edges" in conn.insert_observation_edge_sql


def test_refresh_news_item_observation_summary_requires_cursor_rowcount() -> None:
    conn = ObservationSummaryRefreshConnection(
        row={"news_item_id": "news-1"},
        omit_rowcount=True,
    )
    repo = NewsItemRepository(conn)

    with pytest.raises(TypeError, match="news_repository_rowcount_invalid"):
        repo._refresh_news_item_observation_summary(news_item_id="news-1", now_ms=1_000)

    assert "UPDATE news_items AS items" in conn.summary_sql


@pytest.mark.parametrize("rowcount", [True, False, "1", None, -1, 0, 2])
def test_refresh_news_item_observation_summary_rejects_invalid_or_mismatched_rowcount(
    rowcount: object,
) -> None:
    conn = ObservationSummaryRefreshConnection(
        row={"news_item_id": "news-1"},
        rowcount=rowcount,
    )
    repo = NewsItemRepository(conn)

    with pytest.raises(TypeError, match="news_repository_rowcount_invalid"):
        repo._refresh_news_item_observation_summary(news_item_id="news-1", now_ms=1_000)

    assert "UPDATE news_items AS items" in conn.summary_sql


def test_refresh_news_item_observation_summary_rejects_missing_required_row_without_fallback_select() -> None:
    conn = ObservationSummaryRefreshConnection(
        row=None,
        rowcount=1,
        fallback_row={"news_item_id": "news-1"},
    )
    repo = NewsItemRepository(conn)

    with pytest.raises(TypeError, match="news_repository_rowcount_invalid"):
        repo._refresh_news_item_observation_summary(news_item_id="news-1", now_ms=1_000)

    assert conn.fallback_select_count == 0


def test_refresh_news_item_observation_summary_accepts_matching_required_row() -> None:
    conn = ObservationSummaryRefreshConnection(
        row={"news_item_id": "news-1", "duplicate_observation_count": 2},
        rowcount=1,
    )
    repo = NewsItemRepository(conn)

    row = repo._refresh_news_item_observation_summary(news_item_id="news-1", now_ms=1_000)

    assert row["news_item_id"] == "news-1"
    assert row["duplicate_observation_count"] == 2
    assert conn.fallback_select_count == 0


def test_refresh_news_item_observation_summary_allows_optional_no_row_without_fallback_select() -> None:
    conn = ObservationSummaryRefreshConnection(
        row=None,
        rowcount=0,
        fallback_row={"news_item_id": "news-old"},
    )
    repo = NewsItemRepository(conn)

    row = repo._refresh_news_item_observation_summary(
        news_item_id="news-old",
        now_ms=1_000,
        required=False,
    )

    assert row == {}
    assert conn.fallback_select_count == 0


@pytest.mark.parametrize(
    ("side", "field_name", "bad_value"),
    [
        ("existing", "duplicate_observation_count", None),
        ("existing", "duplicate_observation_count", "1"),
        ("existing", "duplicate_observation_count", True),
        ("updated", "duplicate_observation_count", -1),
        ("existing", "source_ids_json", None),
        ("existing", "source_ids_json", {}),
        ("updated", "source_domains_json", "[]"),
        ("updated", "provider_article_keys_json", {}),
    ],
)
def test_news_item_aggregate_changed_rejects_malformed_summary_fields(
    side: str,
    field_name: str,
    bad_value: object,
) -> None:
    existing = _valid_news_item_aggregate_row()
    updated = _valid_news_item_aggregate_row()
    {"existing": existing, "updated": updated}[side][field_name] = bad_value

    with pytest.raises(ValueError, match=f"news_item_aggregate_{field_name}_required"):
        _news_item_aggregate_changed(existing, updated)


def test_reselect_news_item_representative_returning_requires_cursor_rowcount() -> None:
    conn = ReselectRepresentativeReturningConnection(
        row={"news_item_id": "news-old"},
        omit_rowcount=True,
    )
    repo = NewsItemRepository(conn)

    with pytest.raises(TypeError, match="news_repository_rowcount_invalid"):
        repo._reselect_news_item_representative_from_edges(news_item_id="news-old", now_ms=1_000)

    assert "WITH representative_edge AS" in conn.reselect_sql
    assert "UPDATE news_items AS items" in conn.reselect_sql


@pytest.mark.parametrize("rowcount", [True, False, "1", None, -1, 0, 2])
def test_reselect_news_item_representative_returning_rejects_invalid_or_mismatched_rowcount(
    rowcount: object,
) -> None:
    conn = ReselectRepresentativeReturningConnection(
        row={"news_item_id": "news-old"},
        rowcount=rowcount,
    )
    repo = NewsItemRepository(conn)

    with pytest.raises(TypeError, match="news_repository_rowcount_invalid"):
        repo._reselect_news_item_representative_from_edges(news_item_id="news-old", now_ms=1_000)

    assert "RETURNING items.*" in conn.reselect_sql


def test_reselect_news_item_representative_returning_rejects_missing_row_for_updated_rowcount() -> None:
    conn = ReselectRepresentativeReturningConnection(row=None, rowcount=1)
    repo = NewsItemRepository(conn)

    with pytest.raises(TypeError, match="news_repository_rowcount_invalid"):
        repo._reselect_news_item_representative_from_edges(news_item_id="news-old", now_ms=1_000)

    assert "RETURNING items.*" in conn.reselect_sql


def test_reselect_news_item_representative_returning_accepts_zero_row_noop() -> None:
    conn = ReselectRepresentativeReturningConnection(row=None, rowcount=0)
    repo = NewsItemRepository(conn)

    row = repo._reselect_news_item_representative_from_edges(news_item_id="news-old", now_ms=1_000)

    assert row == {}
    assert conn.params == ("news-old", 1_000, "news-old")


def test_reselect_news_item_representative_returning_accepts_matching_optional_row() -> None:
    conn = ReselectRepresentativeReturningConnection(
        row={"news_item_id": "news-old", "provider_item_id": "provider-2"},
        rowcount=1,
    )
    repo = NewsItemRepository(conn)

    row = repo._reselect_news_item_representative_from_edges(news_item_id="news-old", now_ms=1_000)

    assert row["news_item_id"] == "news-old"
    assert row["provider_item_id"] == "provider-2"
    assert conn.params == ("news-old", 1_000, "news-old")


def test_provider_article_edge_remap_returning_counts_require_cursor_rowcount() -> None:
    conn = RemapEdgesReturningConnection(
        rows=[{"old_news_item_id": "news-old"}],
        omit_rowcount=True,
    )
    repo = NewsItemRepository(conn)

    with pytest.raises(TypeError, match="news_repository_rowcount_invalid"):
        repo._remap_provider_article_edges_to_news_item(
            provider_article_key="rss:article-1",
            news_item_id="news-1",
            now_ms=1_000,
        )

    assert "UPDATE news_item_observation_edges AS edges" in conn.remap_sql


@pytest.mark.parametrize("rowcount", [True, False, "1", None, -1, 0, 2])
def test_provider_article_edge_remap_returning_counts_reject_invalid_or_mismatched_rowcount(
    rowcount: object,
) -> None:
    conn = RemapEdgesReturningConnection(
        rows=[{"old_news_item_id": "news-old"}],
        rowcount=rowcount,
    )
    repo = NewsItemRepository(conn)

    with pytest.raises(TypeError, match="news_repository_rowcount_invalid"):
        repo._remap_provider_article_edges_to_news_item(
            provider_article_key="rss:article-1",
            news_item_id="news-1",
            now_ms=1_000,
        )

    assert "UPDATE news_item_observation_edges AS edges" in conn.remap_sql


def test_provider_article_edge_remap_returning_counts_accept_zero_row_noop() -> None:
    conn = RemapEdgesReturningConnection(rows=[], rowcount=0)
    repo = NewsItemRepository(conn)

    old_item_ids = repo._remap_provider_article_edges_to_news_item(
        provider_article_key="rss:article-1",
        news_item_id="news-1",
        now_ms=1_000,
    )

    assert old_item_ids == []
    assert "UPDATE news_item_observation_edges AS edges" in conn.remap_sql


def test_provider_article_edge_remap_returning_counts_accept_matching_rows() -> None:
    conn = RemapEdgesReturningConnection(
        rows=[{"old_news_item_id": "news-old"}],
        rowcount=1,
    )
    repo = NewsItemRepository(conn)

    old_item_ids = repo._remap_provider_article_edges_to_news_item(
        provider_article_key="rss:article-1",
        news_item_id="news-1",
        now_ms=1_000,
    )

    assert old_item_ids == ["news-old"]
    assert "UPDATE news_item_observation_edges AS edges" in conn.remap_sql


def test_material_duplicate_edge_remap_returning_counts_require_cursor_rowcount() -> None:
    conn = RemapEdgesReturningConnection(
        rows=[{"old_news_item_id": "news-old"}],
        omit_rowcount=True,
        candidate_rows=[_material_duplicate_candidate_row()],
    )
    repo = NewsItemRepository(conn)

    with pytest.raises(TypeError, match="news_repository_rowcount_invalid"):
        _remap_material_duplicate_edges(repo)

    assert "UPDATE news_item_observation_edges AS edges" in conn.remap_sql


@pytest.mark.parametrize("rowcount", [True, False, "1", None, -1, 0, 2])
def test_material_duplicate_edge_remap_returning_counts_reject_invalid_or_mismatched_rowcount(
    rowcount: object,
) -> None:
    conn = RemapEdgesReturningConnection(
        rows=[{"old_news_item_id": "news-old"}],
        rowcount=rowcount,
        candidate_rows=[_material_duplicate_candidate_row()],
    )
    repo = NewsItemRepository(conn)

    with pytest.raises(TypeError, match="news_repository_rowcount_invalid"):
        _remap_material_duplicate_edges(repo)

    assert "UPDATE news_item_observation_edges AS edges" in conn.remap_sql


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [
        pytest.param("raw_observation_count", None, id="missing_raw_observation_count"),
        pytest.param("canonical_item_count", "1", id="string_canonical_item_count"),
        pytest.param("observation_edge_count", True, id="bool_observation_edge_count"),
        pytest.param("enabled_serving_row_count", -1, id="negative_enabled_serving_row_count"),
        pytest.param("top_visible_content_duplicate_groups", {}, id="mapping_top_content_groups"),
        pytest.param("material_title_duplicate_groups", [], id="list_material_title_groups"),
        pytest.param("source_sync_diagnostics", None, id="missing_source_sync_diagnostics"),
    ],
)
def test_news_dedup_diagnostics_rejects_malformed_summary_row(
    field_name: str,
    bad_value: object,
) -> None:
    row = _valid_news_dedup_diagnostics_row()
    row[field_name] = bad_value
    conn = DedupDiagnosticsConnection(summary_row=row)
    repo = NewsPageRepository(conn)

    with pytest.raises(ValueError, match=f"news_dedup_diagnostics_{field_name}_required"):
        repo.news_dedup_diagnostics(window_ms=1_000, now_ms=1_779_000_000_000)


def test_news_dedup_diagnostics_uses_explicit_positive_window() -> None:
    conn = DedupDiagnosticsConnection(summary_row=_valid_news_dedup_diagnostics_row())
    repo = NewsPageRepository(conn)

    result = repo.news_dedup_diagnostics(window_ms=1_000, now_ms=1_779_000_000_000)

    assert result["raw_observation_count"] == 1
    first_params = conn.statements[0][1]
    current_policy_params = conn.statements[2][1]
    assert isinstance(first_params, dict)
    assert first_params["now_ms"] == 1_779_000_000_000
    assert first_params["window_ms"] == 1_000
    assert isinstance(current_policy_params, dict)
    assert current_policy_params == {"now_ms": 1_779_000_000_000, "window_ms": 1_000}


@pytest.mark.parametrize("window_ms", [0, -1, True, "1000"])
def test_news_dedup_diagnostics_rejects_malformed_window_before_sql(window_ms: object) -> None:
    conn = DedupDiagnosticsConnection(summary_row=_valid_news_dedup_diagnostics_row())
    repo = NewsPageRepository(conn)

    with pytest.raises(ValueError, match="news_dedup_diagnostics_window_ms_required"):
        repo.news_dedup_diagnostics(window_ms=window_ms, now_ms=1_779_000_000_000)  # type: ignore[arg-type]

    assert conn.statements == []


def test_current_policy_material_duplicate_groups_reports_valid_opennews_duplicates() -> None:
    groups = _current_policy_material_duplicate_groups(
        [
            _current_policy_material_row(news_item_id="news-1"),
            _current_policy_material_row(news_item_id="news-2", published_at_ms=1_230_000),
            _current_policy_material_row(provider_type="rss", news_item_id="news-rss"),
        ]
    )

    assert groups == [
        {
            "source_id": "opennews-news",
            "title_fingerprint": "bitcoin crashes as billions of longs get liquidated",
            "row_count": 2,
            "duplicate_rows": 1,
            "news_item_ids": ["news-1", "news-2"],
        }
    ]


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [
        ("provider_type", None),
        ("provider_type", ""),
        ("provider_type", 123),
        ("source_id", None),
        ("source_id", ""),
        ("source_id", 123),
        ("news_item_id", None),
        ("news_item_id", ""),
        ("news_item_id", 123),
        ("title", None),
        ("title", ""),
        ("title", 123),
        ("published_at_ms", None),
        ("published_at_ms", 0),
        ("published_at_ms", -1),
        ("published_at_ms", True),
        ("published_at_ms", "1200000"),
        ("provider_token_impacts_json", None),
        ("provider_token_impacts_json", '[{"symbol":"BTC"}]'),
        ("provider_token_impacts_json", 123),
    ],
)
def test_current_policy_material_duplicate_groups_rejects_malformed_opennews_rows(
    field_name: str,
    bad_value: object,
) -> None:
    row = _current_policy_material_row()
    row[field_name] = bad_value

    with pytest.raises(ValueError, match=f"news_dedup_current_policy_material_{field_name}_required"):
        _current_policy_material_duplicate_groups([row])


def test_current_policy_material_duplicate_groups_rejects_missing_opennews_contract_fields() -> None:
    row = _current_policy_material_row()
    row.pop("provider_token_impacts_json")

    with pytest.raises(ValueError, match="news_dedup_current_policy_material_provider_token_impacts_json_required"):
        _current_policy_material_duplicate_groups([row])


def test_current_policy_material_duplicate_groups_skips_non_opennews_after_provider_type_validation() -> None:
    groups = _current_policy_material_duplicate_groups(
        [
            {
                "provider_type": "rss",
                "source_id": 123,
                "news_item_id": 456,
                "published_at_ms": None,
            }
        ]
    )

    assert groups == []


def test_disable_unconfigured_sources_returning_counts_require_cursor_rowcount() -> None:
    conn = DisableUnconfiguredSourceRowsConnection(
        rows=[{"source_id": "stale-source"}],
        omit_rowcount=True,
    )
    repo = NewsSourceRepository(conn)

    with pytest.raises(TypeError, match="news_repository_rowcount_invalid"):
        repo.disable_unconfigured_sources(
            configured_source_ids=["active-source"],
            now_ms=1_000,
        )


@pytest.mark.parametrize("rowcount", [True, False, "1", None, -1, 0, 2])
def test_disable_unconfigured_sources_returning_counts_reject_invalid_or_mismatched_rowcount(
    rowcount: object,
) -> None:
    conn = DisableUnconfiguredSourceRowsConnection(
        rows=[{"source_id": "stale-source"}],
        rowcount=rowcount,
    )
    repo = NewsSourceRepository(conn)

    with pytest.raises(TypeError, match="news_repository_rowcount_invalid"):
        repo.disable_unconfigured_sources(
            configured_source_ids=["active-source"],
            now_ms=1_000,
        )


def test_claim_due_sources_returning_counts_require_cursor_rowcount() -> None:
    conn = ClaimDueSourcesConnection(
        rows=[{"source_id": "source-1"}],
        omit_rowcount=True,
    )
    repo = NewsSourceRepository(conn)

    with pytest.raises(TypeError, match="news_repository_rowcount_invalid"):
        repo.claim_due_sources(
            now_ms=1_000,
            limit=1,
            claim_lease_ms=60_000,
        )


@pytest.mark.parametrize("rowcount", [True, False, "1", None, -1, 0, 2])
def test_claim_due_sources_returning_counts_reject_invalid_or_mismatched_rowcount(
    rowcount: object,
) -> None:
    conn = ClaimDueSourcesConnection(
        rows=[{"source_id": "source-1"}],
        rowcount=rowcount,
    )
    repo = NewsSourceRepository(conn)

    with pytest.raises(TypeError, match="news_repository_rowcount_invalid"):
        repo.claim_due_sources(
            now_ms=1_000,
            limit=1,
            claim_lease_ms=60_000,
        )


def test_claim_due_sources_returning_counts_accept_zero_row_noop() -> None:
    conn = ClaimDueSourcesConnection(rows=[], rowcount=0)
    repo = NewsSourceRepository(conn)

    rows = repo.claim_due_sources(
        now_ms=1_000,
        limit=1,
        claim_lease_ms=60_000,
    )

    assert rows == []


def test_claim_due_sources_returning_counts_accept_matching_claim_rows() -> None:
    conn = ClaimDueSourcesConnection(rows=[{"source_id": "source-1"}], rowcount=1)
    repo = NewsSourceRepository(conn)

    rows = repo.claim_due_sources(
        now_ms=1_000,
        limit=1,
        claim_lease_ms=60_000,
    )

    assert rows == [{"source_id": "source-1"}]
    assert conn.params == (1_000, 1, 61_000, 1_000)


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        pytest.param({"limit": -1}, "news_source_claim_limit_required", id="negative-limit"),
        pytest.param({"limit": True}, "news_source_claim_limit_required", id="bool-limit"),
        pytest.param({"limit": "1"}, "news_source_claim_limit_required", id="string-limit"),
        pytest.param({"claim_lease_ms": 0}, "news_source_claim_lease_ms_required", id="zero-lease"),
        pytest.param({"claim_lease_ms": True}, "news_source_claim_lease_ms_required", id="bool-lease"),
        pytest.param({"claim_lease_ms": "60000"}, "news_source_claim_lease_ms_required", id="string-lease"),
    ],
)
def test_claim_due_sources_rejects_malformed_parameters_before_sql(
    overrides: dict[str, object],
    error: str,
) -> None:
    conn = ClaimDueSourcesConnection(rows=[], rowcount=0)
    repo = NewsSourceRepository(conn)
    params: dict[str, object] = {
        "now_ms": 1_000,
        "limit": 1,
        "claim_lease_ms": 60_000,
    }
    params.update(overrides)

    with pytest.raises(ValueError, match=error):
        repo.claim_due_sources(**params)

    assert conn.statements == []


def test_start_fetch_run_requires_fetch_run_insert_rowcount_before_source_update() -> None:
    conn = StartFetchRunConnection(insert_omit_rowcount=True, source_rowcount=1)
    repo = NewsSourceRepository(conn)

    with pytest.raises(TypeError, match="news_repository_rowcount_invalid"):
        _start_fetch_run(repo)

    assert len(conn.statements) == 1
    assert "INSERT INTO news_fetch_runs" in conn.statements[0][0]


@pytest.mark.parametrize("rowcount", [True, False, "1", None, -1, 0, 2])
def test_start_fetch_run_rejects_invalid_fetch_run_insert_rowcount(rowcount: object) -> None:
    conn = StartFetchRunConnection(insert_rowcount=rowcount, source_rowcount=1)
    repo = NewsSourceRepository(conn)

    with pytest.raises(TypeError, match="news_repository_rowcount_invalid"):
        _start_fetch_run(repo)

    assert len(conn.statements) == 1
    assert "INSERT INTO news_fetch_runs" in conn.statements[0][0]


def test_start_fetch_run_requires_source_update_rowcount_before_returning_run_id() -> None:
    conn = StartFetchRunConnection(insert_rowcount=1, source_omit_rowcount=True)
    repo = NewsSourceRepository(conn)

    with pytest.raises(TypeError, match="news_repository_rowcount_invalid"):
        _start_fetch_run(repo)

    assert len(conn.statements) == 2
    assert "UPDATE news_sources" in conn.statements[1][0]


@pytest.mark.parametrize("rowcount", [True, False, "1", None, -1, 0, 2])
def test_start_fetch_run_rejects_invalid_source_update_rowcount(rowcount: object) -> None:
    conn = StartFetchRunConnection(insert_rowcount=1, source_rowcount=rowcount)
    repo = NewsSourceRepository(conn)

    with pytest.raises(TypeError, match="news_repository_rowcount_invalid"):
        _start_fetch_run(repo)

    assert len(conn.statements) == 2
    assert "UPDATE news_sources" in conn.statements[1][0]


def test_start_fetch_run_accepts_matching_insert_and_source_update_rowcounts() -> None:
    conn = StartFetchRunConnection(insert_rowcount=1, source_rowcount=1)
    repo = NewsSourceRepository(conn)

    fetch_run_id = _start_fetch_run(repo)

    assert fetch_run_id.startswith("news-fetch-run-")
    assert len(conn.statements) == 2
    assert "INSERT INTO news_fetch_runs" in conn.statements[0][0]
    assert "UPDATE news_sources" in conn.statements[1][0]


def test_finish_fetch_run_returning_row_requires_cursor_rowcount() -> None:
    conn = FinishFetchRunConnection(row={"fetch_run_id": "run-1"}, omit_rowcount=True)
    repo = NewsSourceRepository(conn)

    with pytest.raises(TypeError, match="news_repository_rowcount_invalid"):
        _finish_fetch_run(repo)

    assert len(conn.statements) == 1


@pytest.mark.parametrize("rowcount", [True, False, "1", None, -1, 0, 2])
def test_finish_fetch_run_returning_row_rejects_invalid_or_mismatched_rowcount(
    rowcount: object,
) -> None:
    conn = FinishFetchRunConnection(row={"fetch_run_id": "run-1"}, rowcount=rowcount)
    repo = NewsSourceRepository(conn)

    with pytest.raises(TypeError, match="news_repository_rowcount_invalid"):
        _finish_fetch_run(repo)

    assert len(conn.statements) == 1


@pytest.mark.parametrize("rowcount", [0, 1])
def test_finish_fetch_run_returning_row_rejects_missing_required_row(rowcount: object) -> None:
    conn = FinishFetchRunConnection(row=None, rowcount=rowcount)
    repo = NewsSourceRepository(conn)

    with pytest.raises(TypeError, match="news_repository_rowcount_invalid"):
        _finish_fetch_run(repo)

    assert len(conn.statements) == 1


def test_finish_fetch_run_returning_row_accepts_matching_required_row() -> None:
    conn = FinishFetchRunConnection(row={"fetch_run_id": "run-1", "status": "success"}, rowcount=1)
    repo = NewsSourceRepository(conn)

    row = _finish_fetch_run(repo)

    assert row == {"fetch_run_id": "run-1", "status": "success"}
    assert len(conn.statements) == 2
    assert "UPDATE news_fetch_runs" in conn.statements[0][0]
    assert "UPDATE news_sources" in conn.statements[1][0]


def test_finish_fetch_run_requires_source_status_update_rowcount_before_returning_run() -> None:
    conn = FinishFetchRunConnection(
        row={"fetch_run_id": "run-1", "status": "success"},
        rowcount=1,
        source_omit_rowcount=True,
    )

    with pytest.raises(TypeError, match="news_repository_rowcount_invalid"):
        _finish_fetch_run(NewsSourceRepository(conn))

    assert len(conn.statements) == 2
    assert "UPDATE news_sources" in conn.statements[1][0]


@pytest.mark.parametrize("rowcount", [True, False, "1", None, -1, 0, 2])
def test_finish_fetch_run_rejects_invalid_source_status_update_rowcount(rowcount: object) -> None:
    conn = FinishFetchRunConnection(
        row={"fetch_run_id": "run-1", "status": "success"},
        rowcount=1,
        source_rowcount=rowcount,
    )

    with pytest.raises(TypeError, match="news_repository_rowcount_invalid"):
        _finish_fetch_run(NewsSourceRepository(conn))

    assert len(conn.statements) == 2
    assert "UPDATE news_sources" in conn.statements[1][0]


@pytest.mark.parametrize(
    ("field_name", "kwargs"),
    [
        ("fetched_count", {"fetched_count": None, "items_seen": None}),
        ("inserted_count", {"inserted_count": None, "items_inserted": None}),
        ("updated_count", {"updated_count": None, "items_updated": None}),
        ("duplicate_count", {"duplicate_count": None}),
        ("fetched_count", {"fetched_count": True}),
        ("inserted_count", {"inserted_count": "1"}),
        ("updated_count", {"updated_count": -1}),
        ("duplicate_count", {"duplicate_count": False}),
    ],
)
def test_finish_fetch_run_requires_explicit_nonnegative_counts(
    field_name: str,
    kwargs: dict[str, object],
) -> None:
    conn = FinishFetchRunConnection(row={"fetch_run_id": "run-1", "status": "success"}, rowcount=1)
    repo = NewsSourceRepository(conn)

    payload: dict[str, object] = {
        "fetch_run_id": "run-1",
        "source_id": "source-1",
        "status": "success",
        "finished_at_ms": 1_000,
        "fetched_count": 1,
        "inserted_count": 1,
        "updated_count": 0,
        "duplicate_count": 0,
    }
    payload.update(kwargs)

    with pytest.raises(ValueError, match=f"news_fetch_run_{field_name}_required"):
        repo.finish_fetch_run(**payload)  # type: ignore[arg-type]

    assert conn.statements == []


@pytest.mark.parametrize(
    ("field_name", "kwargs"),
    [
        ("status", {"status": None}),
        ("status", {"status": ""}),
        ("status", {"status": "running"}),
        ("finished_at_ms", {"finished_at_ms": None}),
        ("finished_at_ms", {"finished_at_ms": True}),
        ("finished_at_ms", {"finished_at_ms": "1000"}),
        ("finished_at_ms", {"finished_at_ms": -1}),
        ("http_status", {"http_status": True}),
        ("http_status", {"http_status": "200"}),
        ("http_status", {"http_status": -1}),
        ("extra_json", {"extra_json": []}),
        ("extra_json", {"extra_json": "{}"}),
    ],
)
def test_finish_fetch_run_requires_explicit_completion_scalar_contract(
    field_name: str,
    kwargs: dict[str, object],
) -> None:
    conn = FinishFetchRunConnection(row={"fetch_run_id": "run-1", "status": "success"}, rowcount=1)
    repo = NewsSourceRepository(conn)

    payload: dict[str, object] = {
        "fetch_run_id": "run-1",
        "source_id": "source-1",
        "status": "success",
        "finished_at_ms": 1_000,
        "fetched_count": 1,
        "inserted_count": 1,
        "updated_count": 0,
        "duplicate_count": 0,
        "http_status": 200,
        "extra_json": {"provider": "opennews"},
    }
    payload.update(kwargs)

    with pytest.raises(ValueError, match=f"news_fetch_run_{field_name}_required"):
        repo.finish_fetch_run(**payload)  # type: ignore[arg-type]

    assert conn.statements == []


def test_news_current_fact_writes_reject_reflective_payload_objects_before_insert() -> None:
    conn = CapturingConnection()
    repo = NewsItemRepository(conn)

    with pytest.raises(ValueError, match="news entity payload"):
        repo.replace_item_entities(
            news_item_id="news-1",
            entities=[SimpleNamespace(entity_id="entity-1", news_item_id="news-1")],
        )

    with pytest.raises(ValueError, match="news token mention payload"):
        repo.replace_token_mentions(
            news_item_id="news-1",
            mentions=[SimpleNamespace(mention_id="mention-1", news_item_id="news-1")],
        )

    with pytest.raises(ValueError, match="news fact candidate payload"):
        repo.replace_fact_candidates(
            news_item_id="news-1",
            candidates=[SimpleNamespace(fact_candidate_id="fact-1", news_item_id="news-1")],
        )

    assert not any("INSERT INTO news_item_entities" in sql for sql, _params in conn.statements)
    assert not any("INSERT INTO news_token_mentions" in sql for sql, _params in conn.statements)
    assert not any("INSERT INTO news_fact_candidates" in sql for sql, _params in conn.statements)


@pytest.mark.parametrize(
    ("market_scope", "story_identity", "match"),
    [
        (
            NewsMarketScope(
                scope=("crypto",),
                primary="",
                status="classified",
                reason="crypto_evidence",
                basis={},
                version=NEWS_MARKET_SCOPE_VERSION,
            ),
            NewsStoryIdentity(
                story_key="news-story:event:exchange-listing:upbit:ctr:btc-usdt:t20613",
                confidence="strong",
                basis={
                    "method": "exchange_listing_event_key",
                    "subject": "exchange-listing:upbit:ctr:btc-usdt",
                },
                version=NEWS_STORY_IDENTITY_VERSION,
            ),
            "blank primary",
        ),
        (
            NewsMarketScope(
                scope=("crypto",),
                primary="crypto",
                status="classified",
                reason="crypto_evidence",
                basis={"crypto_evidence": ["resolved_crypto_target:cex:BTC"]},
                version=NEWS_MARKET_SCOPE_VERSION,
            ),
            NewsStoryIdentity(story_key="", confidence="strong", basis={}, version=NEWS_STORY_IDENTITY_VERSION),
            "blank story_key",
        ),
    ],
)
def test_update_item_market_scope_and_story_identity_rejects_blank_required_fields(
    market_scope: NewsMarketScope,
    story_identity: NewsStoryIdentity,
    match: str,
) -> None:
    conn = CapturingConnection()
    repo = NewsItemRepository(conn)

    with pytest.raises(ValueError, match=match):
        repo.update_item_market_scope_and_story_identity(
            news_item_id="news-1",
            market_scope=market_scope,
            story_identity=story_identity,
            now_ms=1_000,
        )

    assert conn.statements == []


@pytest.mark.parametrize(
    ("market_scope", "story_identity", "match"),
    [
        (
            NewsMarketScope(
                scope="crypto",
                primary="crypto",
                status="classified",
                reason="crypto_evidence",
                basis={},
                version=NEWS_MARKET_SCOPE_VERSION,
            ),
            NewsStoryIdentity(
                story_key="news-story:event:exchange-listing:upbit:ctr:btc-usdt:t20613",
                confidence="strong",
                basis={
                    "method": "exchange_listing_event_key",
                    "subject": "exchange-listing:upbit:ctr:btc-usdt",
                },
                version=NEWS_STORY_IDENTITY_VERSION,
            ),
            "market scope payload.*scope must be list",
        ),
        (
            NewsMarketScope(
                scope=("crypto",),
                primary="crypto",
                status="classified",
                reason="crypto_evidence",
                basis=["crypto_evidence"],
                version=NEWS_MARKET_SCOPE_VERSION,
            ),
            NewsStoryIdentity(
                story_key="news-story:event:exchange-listing:upbit:ctr:btc-usdt:t20613",
                confidence="strong",
                basis={
                    "method": "exchange_listing_event_key",
                    "subject": "exchange-listing:upbit:ctr:btc-usdt",
                },
                version=NEWS_STORY_IDENTITY_VERSION,
            ),
            "market scope payload.*basis must be mapping",
        ),
        (
            NewsMarketScope(
                scope=("crypto",),
                primary="crypto",
                status="classified",
                reason="crypto_evidence",
                basis={"crypto_evidence": ["resolved_crypto_target:cex:BTC"]},
                version=NEWS_MARKET_SCOPE_VERSION,
            ),
            NewsStoryIdentity(
                story_key="news-story:event:exchange-listing:upbit:ctr:btc-usdt:t20613",
                confidence="strong",
                basis=["exchange_listing_event_key"],
                version=NEWS_STORY_IDENTITY_VERSION,
            ),
            "story identity payload.*basis must be mapping",
        ),
    ],
)
def test_update_item_market_scope_and_story_identity_rejects_invalid_nested_fields(
    market_scope: NewsMarketScope,
    story_identity: NewsStoryIdentity,
    match: str,
) -> None:
    conn = CapturingConnection()
    repo = NewsItemRepository(conn)

    with pytest.raises(ValueError, match=match):
        repo.update_item_market_scope_and_story_identity(
            news_item_id="news-1",
            market_scope=market_scope,
            story_identity=story_identity,
            now_ms=1_000,
        )

    assert conn.statements == []


def test_update_item_market_scope_and_story_identity_writes_current_fields_only() -> None:
    conn = CapturingConnection()
    repo = NewsItemRepository(conn)

    repo.update_item_market_scope_and_story_identity(
        news_item_id="news-1",
        market_scope=_valid_market_scope(),
        story_identity=_valid_story_identity(),
        now_ms=1_000,
    )

    assert "market_scope_json = %s" in conn.sql
    assert "story_key = %s" in conn.sql
    assert "story_identity_json = %s" in conn.sql
    assert "story_identity_version = %s" in conn.sql
    assert "updated_at_ms = %s" in conn.sql
    assert "analysis_admission" not in conn.sql
    assert conn.params[1] == "news-story:event:exchange-listing:upbit:ctr:btc-usdt:t20613"
    assert conn.params[3] == "news_story_identity_v2"
    assert conn.params[4] == 1_000
    assert conn.params[5] == "news-1"


def test_update_item_market_scope_and_agent_admission_writes_current_fields_only() -> None:
    conn = CapturingConnection()
    repo = NewsItemRepository(conn)

    repo.update_item_market_scope_and_agent_admission(
        news_item_id="news-1",
        market_scope=_valid_market_scope(),
        story_identity=_valid_story_identity(),
        admission=_valid_agent_admission(),
        now_ms=1_000,
    )

    assert "market_scope_json = %s" in conn.sql
    assert "story_key = %s" in conn.sql
    assert "agent_admission_status = %s" in conn.sql
    assert "agent_admission_reason = %s" in conn.sql
    assert "agent_representative_news_item_id = %s" in conn.sql
    assert "analysis_admission" not in conn.sql
    assert conn.params[1] == "news-story:event:exchange-listing:upbit:ctr:btc-usdt:t20613"
    assert conn.params[4] == "eligible"
    assert conn.params[5] == "eligible"
    assert conn.params[8] == "news-1"
    assert conn.params[11] == "news-1"


def test_material_duplicate_lock_covers_candidate_window_without_symbol_partition() -> None:
    conn = CapturingConnection()
    repo = NewsItemRepository(conn)

    repo._lock_material_duplicate_candidate_window(
        source_id="opennews-news",
        material_fingerprint="bitcoin crashes as billions of longs get liquidated",
        published_at_ms=1_200_000,
    )

    lock_keys = [
        json.loads(params[0])
        for sql, params in conn.statements
        if "pg_advisory_xact_lock" in sql and isinstance(params, tuple)
    ]
    assert lock_keys == [
        [
            "news-material-duplicate-v2",
            "opennews-news",
            "bitcoin crashes as billions of longs get liquidated",
            600_000,
        ],
        [
            "news-material-duplicate-v2",
            "opennews-news",
            "bitcoin crashes as billions of longs get liquidated",
            1_200_000,
        ],
        [
            "news-material-duplicate-v2",
            "opennews-news",
            "bitcoin crashes as billions of longs get liquidated",
            1_800_000,
        ],
    ]


def test_edge_remap_cleanup_locks_old_news_item_row_before_delete() -> None:
    conn = CapturingConnection()
    repo = NewsItemRepository(conn)

    assert repo._lock_news_item_for_edge_remap_cleanup(news_item_id="news-old") is True

    assert "FROM news_items" in conn.sql
    assert "WHERE news_item_id = %s" in conn.sql
    assert "FOR UPDATE" in conn.sql
    assert conn.params == ("news-old",)


def test_edge_remap_agent_output_guard_uses_story_agent_outputs_only() -> None:
    conn = SourceSyncCursorConnection(row={"has_agent_outputs": False})
    repo = NewsItemRepository(conn)

    assert repo._news_item_has_agent_outputs(news_item_id="news-old") is False

    assert "news_item_agent_runs" not in conn.sql
    assert "news_item_agent_briefs" not in conn.sql
    assert "news_story_agent_runs" in conn.sql
    assert "news_story_agent_briefs" in conn.sql
    assert conn.params == ("news-old", "news-old")


def test_delete_zero_edge_news_item_returning_requires_cursor_rowcount() -> None:
    conn = DeleteReturningConnection(rows=[{"news_item_id": "news-old"}], omit_rowcount=True)
    repo = NewsItemRepository(conn)

    with pytest.raises(TypeError, match="news_repository_rowcount_invalid"):
        repo._delete_zero_edge_news_item(news_item_id="news-old")


@pytest.mark.parametrize("rowcount", [True, False, "1", None, -1, 0, 2])
def test_delete_zero_edge_news_item_returning_rejects_invalid_or_mismatched_rowcount(rowcount: object) -> None:
    conn = DeleteReturningConnection(rows=[{"news_item_id": "news-old"}], rowcount=rowcount)
    repo = NewsItemRepository(conn)

    with pytest.raises(TypeError, match="news_repository_rowcount_invalid"):
        repo._delete_zero_edge_news_item(news_item_id="news-old")


def test_delete_zero_edge_news_item_returning_rejects_missing_returned_row_for_deleted_rowcount() -> None:
    conn = DeleteReturningConnection(rows=[], rowcount=1)
    repo = NewsItemRepository(conn)

    with pytest.raises(TypeError, match="news_repository_rowcount_invalid"):
        repo._delete_zero_edge_news_item(news_item_id="news-old")


def test_news_page_row_returning_write_requires_cursor_rowcount() -> None:
    conn = PageRowReturningConnection(returned_row={"inserted": True}, omit_rowcount=True)
    repo = NewsPageRepository(conn)

    with pytest.raises(TypeError, match="news_repository_rowcount_invalid"):
        repo.replace_page_rows_for_items(news_item_ids=[], rows=[_valid_news_page_row()])


@pytest.mark.parametrize("rowcount", [True, False, "1", None, -1, 0, 2])
def test_news_page_row_returning_write_rejects_invalid_or_mismatched_rowcount(rowcount: object) -> None:
    conn = PageRowReturningConnection(returned_row={"inserted": True}, rowcount=rowcount)
    repo = NewsPageRepository(conn)

    with pytest.raises(TypeError, match="news_repository_rowcount_invalid"):
        repo.replace_page_rows_for_items(news_item_ids=[], rows=[_valid_news_page_row()])


def test_news_page_row_returning_write_accepts_zero_row_unchanged() -> None:
    conn = PageRowReturningConnection(returned_row=None, rowcount=0)
    repo = NewsPageRepository(conn)

    result = repo.replace_page_rows_for_items(news_item_ids=[], rows=[_valid_news_page_row()])

    assert result == {"inserted": 0, "updated": 0, "unchanged": 1, "deleted": 0}


def test_news_page_row_returning_write_counts_insert_after_rowcount_match() -> None:
    conn = PageRowReturningConnection(returned_row={"inserted": True}, rowcount=1)
    repo = NewsPageRepository(conn)

    result = repo.replace_page_rows_for_items(news_item_ids=[], rows=[_valid_news_page_row()])

    assert result == {"inserted": 1, "updated": 0, "unchanged": 0, "deleted": 0}


def test_insert_news_story_agent_run_requires_explicit_audit_json_fields() -> None:
    conn = AgentReturningConnection(
        row={"run_id": "story-run-1", "story_brief_key": "story-brief-1"},
        rowcount=1,
    )
    repo = NewsStoryAgentRepository(conn)
    payload = _news_story_agent_run_payload()
    payload.pop("request_json")

    with pytest.raises(TypeError, match="missing 1 required keyword-only argument: 'request_json'"):
        repo.insert_news_story_agent_run(**payload)

    assert conn.write_sql == ""


def test_insert_news_story_agent_run_rejects_blank_backend() -> None:
    conn = AgentReturningConnection(
        row={"run_id": "story-run-1", "story_brief_key": "story-brief-1"},
        rowcount=1,
    )
    repo = NewsStoryAgentRepository(conn)
    payload = _news_story_agent_run_payload(backend="")

    with pytest.raises(ValueError, match="unsupported news story agent run payload shape: blank backend"):
        repo.insert_news_story_agent_run(**payload)

    assert conn.write_sql == ""


def test_insert_news_story_agent_run_requires_latency() -> None:
    conn = AgentReturningConnection(
        row={"run_id": "story-run-1", "story_brief_key": "story-brief-1"},
        rowcount=1,
    )
    repo = NewsStoryAgentRepository(conn)
    payload = _news_story_agent_run_payload()
    payload.pop("latency_ms")

    with pytest.raises(TypeError, match="missing 1 required keyword-only argument: 'latency_ms'"):
        repo.insert_news_story_agent_run(**payload)

    assert conn.write_sql == ""


def test_insert_news_story_agent_run_requires_non_empty_member_ids() -> None:
    conn = AgentReturningConnection(
        row={"run_id": "story-run-1", "story_brief_key": "story-brief-1"},
        rowcount=1,
    )
    repo = NewsStoryAgentRepository(conn)
    payload = _news_story_agent_run_payload(member_news_item_ids_json=[])

    with pytest.raises(
        ValueError,
        match="unsupported news story agent run payload shape: member_news_item_ids_json must be non-empty",
    ):
        repo.insert_news_story_agent_run(**payload)

    assert conn.write_sql == ""


def test_upsert_news_story_agent_brief_requires_explicit_brief_json() -> None:
    conn = AgentReturningConnection(
        row={"story_brief_key": "story-brief-1", "agent_run_id": "story-run-1"},
        rowcount=1,
    )
    repo = NewsStoryAgentRepository(conn)
    payload = _news_story_agent_brief_payload()
    payload.pop("brief_json")

    with pytest.raises(TypeError, match="missing 1 required keyword-only argument: 'brief_json'"):
        repo.upsert_news_story_agent_brief(**payload)

    assert conn.write_sql == ""


def test_upsert_news_story_agent_brief_ready_payload_requires_summary_without_market_read_fallback() -> None:
    conn = AgentReturningConnection(
        row={"story_brief_key": "story-brief-1", "agent_run_id": "story-run-1"},
        rowcount=1,
    )
    repo = NewsStoryAgentRepository(conn)
    payload = _news_story_agent_brief_payload(brief_json={"market_read_zh": "Legacy market read is not publishable."})

    with pytest.raises(ValueError, match="ready news story agent brief requires publishable summary"):
        repo.upsert_news_story_agent_brief(**payload)

    assert conn.write_sql == ""


def test_upsert_canonical_news_item_does_not_open_an_implicit_transaction() -> None:
    conn = TransactionRecordingConnection()
    repo = NewsItemRepository(conn)

    with pytest.raises(RuntimeError, match="stop after transaction entry"):
        repo.upsert_canonical_news_item(
            provider_item_id="provider-1",
            canonical_url="https://example.com/news/1",
            title="Headline",
            fetched_at_ms=1,
            content_hash="content-1",
            title_fingerprint="headline",
            now_ms=2,
        )

    assert conn.events == ["execute"]


class CapturingConnection:
    def __init__(self) -> None:
        self.sql = ""
        self.params: object = None
        self.statements: list[tuple[str, object]] = []
        self.events: list[str] = []

    def execute(self, sql: str, params: object = None) -> CapturingCursor:
        self.sql = sql
        self.params = params
        self.statements.append((sql, params))
        return CapturingCursor()

    def transaction(self) -> CapturingConnectionTransaction:
        return CapturingConnectionTransaction(self.events)


class SourceSyncCursorConnection:
    def __init__(self, *, row: dict[str, object]) -> None:
        self.sql = ""
        self.params: object = None
        self.statements: list[tuple[str, object]] = []
        self.row = row

    def execute(self, sql: str, params: object = None) -> NewsItemDetailCursor:
        self.sql = sql
        self.params = params
        self.statements.append((sql, params))
        return NewsItemDetailCursor(row=self.row)


class DedupDiagnosticsConnection:
    def __init__(self, *, summary_row: dict[str, object]) -> None:
        self.sql = ""
        self.params: object = None
        self.statements: list[tuple[str, object]] = []
        self._cursors = [
            NewsItemDetailCursor(row=summary_row),
            NewsItemDetailCursor(rows=[]),
            NewsItemDetailCursor(rows=[]),
            NewsItemDetailCursor(row={"row_count": 0}),
            NewsItemDetailCursor(row={"row_count": 0}),
        ]

    def execute(self, sql: str, params: object = None) -> NewsItemDetailCursor:
        self.sql = sql
        self.params = params
        self.statements.append((sql, params))
        return self._cursors.pop(0)


class NewsItemDetailConnection:
    def __init__(self, *, page_row: dict[str, object], base_row: dict[str, object] | None = None) -> None:
        self.sql = ""
        self.params: object = None
        self.statements: list[tuple[str, object]] = []
        self._cursors = [
            NewsItemDetailCursor(row=base_row or _valid_news_item_detail_base_row()),
            NewsItemDetailCursor(row=page_row),
            NewsItemDetailCursor(rows=[]),
        ]

    def execute(self, sql: str, params: object = None) -> NewsItemDetailCursor:
        self.sql = sql
        self.params = params
        self.statements.append((sql, params))
        return self._cursors.pop(0)


class NewsItemDetailCursor:
    def __init__(
        self,
        *,
        row: dict[str, object] | None = None,
        rows: list[dict[str, object]] | None = None,
    ) -> None:
        self._row = row
        self._rows = rows or []

    def fetchone(self) -> dict[str, object] | None:
        return self._row

    def fetchall(self) -> list[dict[str, object]]:
        return list(self._rows)


class NewsPageRowsConnection:
    def __init__(self, *, rows: list[dict[str, object]]) -> None:
        self.sql = ""
        self.params: object = None
        self.statements: list[tuple[str, object]] = []
        self.rows = rows

    def execute(self, sql: str, params: object = None) -> NewsPageRowsCursor:
        self.sql = sql
        self.params = params
        self.statements.append((sql, params))
        return NewsPageRowsCursor(rows=self.rows)


class NewsPageRowsCursor:
    def __init__(self, *, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    def fetchall(self) -> list[dict[str, object]]:
        return list(self._rows)


class StoryBriefTargetsConnection:
    def __init__(self, *, rows: list[dict[str, object]]) -> None:
        self.sql = ""
        self.params: object = None
        self.statements: list[tuple[str, object]] = []
        self.rows = rows

    def execute(self, sql: str, params: object = None) -> NewsPageRowsCursor:
        self.sql = sql
        self.params = params
        self.statements.append((sql, params))
        return NewsPageRowsCursor(rows=self.rows)


class RowcountConnection:
    def __init__(self, *, rowcount: object = 1, omit_rowcount: bool = False) -> None:
        self.rowcount = rowcount
        self.omit_rowcount = omit_rowcount

    def execute(self, sql: str, params: object = None) -> RowcountCursor:
        return RowcountCursor(rowcount=self.rowcount, omit_rowcount=self.omit_rowcount)


class RowcountCursor:
    def __init__(self, *, rowcount: object = 1, omit_rowcount: bool = False) -> None:
        if not omit_rowcount:
            self.rowcount = rowcount

    def fetchone(self) -> dict[str, Any] | None:
        return None

    def fetchall(self) -> list[dict[str, Any]]:
        return []


class DisableUnconfiguredSourceRowsConnection:
    def __init__(
        self,
        *,
        rows: list[dict[str, object]],
        rowcount: object = 1,
        omit_rowcount: bool = False,
    ) -> None:
        self.rows = rows
        self.rowcount = rowcount
        self.omit_rowcount = omit_rowcount
        self.statements: list[tuple[str, object]] = []

    def execute(self, sql: str, params: object = None) -> DisableUnconfiguredSourceRowsCursor:
        self.statements.append((sql, params))
        return DisableUnconfiguredSourceRowsCursor(
            rows=self.rows,
            rowcount=self.rowcount,
            omit_rowcount=self.omit_rowcount,
        )


class DisableUnconfiguredSourceRowsCursor:
    def __init__(
        self,
        *,
        rows: list[dict[str, object]],
        rowcount: object = 1,
        omit_rowcount: bool = False,
    ) -> None:
        self._rows = rows
        if not omit_rowcount:
            self.rowcount = rowcount

    def fetchall(self) -> list[dict[str, object]]:
        return list(self._rows)


class UpsertSourceConnection:
    def __init__(
        self,
        *,
        existing: dict[str, object] | None,
        row: dict[str, object] | None,
        rowcount: object = 1,
        omit_rowcount: bool = False,
    ) -> None:
        self.existing = existing
        self.row = row
        self.rowcount = rowcount
        self.omit_rowcount = omit_rowcount
        self.statements: list[tuple[str, object]] = []

    def execute(self, sql: str, params: object = None) -> UpsertSourceCursor:
        self.statements.append((sql, params))
        if "SELECT * FROM news_sources WHERE source_id = %s" in sql:
            return UpsertSourceCursor(row=self.existing, rowcount=1)
        if "INSERT INTO news_sources" in sql:
            return UpsertSourceCursor(
                row=self.row,
                rowcount=self.rowcount,
                omit_rowcount=self.omit_rowcount,
            )
        return UpsertSourceCursor(row=None, rowcount=0)


class UpsertSourceCursor:
    def __init__(
        self,
        *,
        row: dict[str, object] | None,
        rowcount: object = 1,
        omit_rowcount: bool = False,
    ) -> None:
        self._row = row
        if not omit_rowcount:
            self.rowcount = rowcount

    def fetchone(self) -> dict[str, object] | None:
        return self._row


class SingleReturningConnection:
    def __init__(self, *, row: dict[str, object], rowcount: object = 1) -> None:
        self.row = row
        self.rowcount = rowcount
        self.statements: list[tuple[str, object]] = []

    def execute(self, sql: str, params: object = None) -> UpsertSourceCursor:
        self.statements.append((sql, params))
        return UpsertSourceCursor(row=self.row, rowcount=self.rowcount)


class UpsertProviderItemConnection:
    def __init__(
        self,
        *,
        existing: dict[str, object] | None,
        row: dict[str, object] | None,
        rowcount: object = 1,
        omit_rowcount: bool = False,
    ) -> None:
        self.existing = existing
        self.row = row
        self.rowcount = rowcount
        self.omit_rowcount = omit_rowcount
        self.statements: list[tuple[str, object]] = []

    def execute(self, sql: str, params: object = None) -> UpsertProviderItemCursor:
        self.statements.append((sql, params))
        if "SELECT provider_type" in sql and "FROM news_sources" in sql:
            return UpsertProviderItemCursor(row={"provider_type": "opennews"}, rowcount=1)
        if "SELECT provider_items.*, sources.provider_type" in sql:
            return UpsertProviderItemCursor(
                row=self.existing,
                rowcount=1 if self.existing is not None else 0,
            )
        if "INSERT INTO news_provider_items" in sql:
            return UpsertProviderItemCursor(
                row=self.row,
                rowcount=self.rowcount,
                omit_rowcount=self.omit_rowcount,
            )
        return UpsertProviderItemCursor(row=None, rowcount=0)


class UpsertProviderItemCursor:
    def __init__(
        self,
        *,
        row: dict[str, object] | None,
        rowcount: object = 1,
        omit_rowcount: bool = False,
    ) -> None:
        self._row = row
        if not omit_rowcount:
            self.rowcount = rowcount

    def fetchone(self) -> dict[str, object] | None:
        return self._row


class UpsertCanonicalNewsItemConnection:
    def __init__(
        self,
        *,
        row: dict[str, object] | None,
        rowcount: object = 1,
        omit_rowcount: bool = False,
        edge_rowcount: object = 1,
        edge_omit_rowcount: bool = False,
    ) -> None:
        self.row = row
        self.rowcount = rowcount
        self.omit_rowcount = omit_rowcount
        self.edge_rowcount = edge_rowcount
        self.edge_omit_rowcount = edge_omit_rowcount
        self.statements: list[tuple[str, object]] = []
        self.insert_news_items_sql = ""
        self.insert_observation_edge_sql = ""

    def execute(self, sql: str, params: object = None) -> UpsertCanonicalNewsItemCursor:
        self.statements.append((sql, params))
        if "FROM news_provider_items AS provider_items" in sql and "WHERE provider_items.provider_item_id" in sql:
            return UpsertCanonicalNewsItemCursor(
                row={
                    "provider_item_id": "provider-item-1",
                    "source_id": "source-1",
                    "source_domain": "example.com",
                    "provider_type": "rss",
                    "provider_article_id": "",
                    "provider_payload_status": "ready",
                },
                rowcount=1,
            )
        if "SELECT pg_advisory_xact_lock" in sql:
            return UpsertCanonicalNewsItemCursor(row=None, rowcount=1)
        if "SELECT * FROM news_items WHERE canonical_item_key = %s" in sql:
            return UpsertCanonicalNewsItemCursor(row=None, rowcount=0)
        if "SELECT * FROM news_item_observation_edges WHERE provider_item_id = %s" in sql:
            return UpsertCanonicalNewsItemCursor(row=None, rowcount=0)
        if "INSERT INTO news_items" in sql:
            self.insert_news_items_sql = sql
            return UpsertCanonicalNewsItemCursor(
                row=self.row,
                rowcount=self.rowcount,
                omit_rowcount=self.omit_rowcount,
            )
        if "INSERT INTO news_item_observation_edges" in sql:
            self.insert_observation_edge_sql = sql
            return UpsertCanonicalNewsItemCursor(
                row=None,
                rowcount=self.edge_rowcount,
                omit_rowcount=self.edge_omit_rowcount,
            )
        return UpsertCanonicalNewsItemCursor(row=None, rowcount=0)


class UpsertCanonicalNewsItemCursor:
    def __init__(
        self,
        *,
        row: dict[str, object] | None,
        rowcount: object = 1,
        omit_rowcount: bool = False,
    ) -> None:
        self._row = row
        if not omit_rowcount:
            self.rowcount = rowcount

    def fetchone(self) -> dict[str, object] | None:
        return self._row


class ObservationSummaryRefreshConnection:
    def __init__(
        self,
        *,
        row: dict[str, object] | None,
        rowcount: object = 1,
        omit_rowcount: bool = False,
        fallback_row: dict[str, object] | None = None,
    ) -> None:
        self.row = row
        self.rowcount = rowcount
        self.omit_rowcount = omit_rowcount
        self.fallback_row = fallback_row
        self.summary_sql = ""
        self.fallback_select_count = 0
        self.statements: list[tuple[str, object]] = []

    def execute(self, sql: str, params: object = None) -> ObservationSummaryRefreshCursor:
        self.statements.append((sql, params))
        if "WITH edge_summary AS" in sql and "UPDATE news_items AS items" in sql:
            self.summary_sql = sql
            return ObservationSummaryRefreshCursor(
                row=self.row,
                rowcount=self.rowcount,
                omit_rowcount=self.omit_rowcount,
            )
        if "SELECT * FROM news_items WHERE news_item_id" in sql:
            self.fallback_select_count += 1
            return ObservationSummaryRefreshCursor(
                row=self.fallback_row,
                rowcount=1 if self.fallback_row is not None else 0,
            )
        return ObservationSummaryRefreshCursor(row=None, rowcount=0)


class ObservationSummaryRefreshCursor:
    def __init__(
        self,
        *,
        row: dict[str, object] | None,
        rowcount: object = 1,
        omit_rowcount: bool = False,
    ) -> None:
        self._row = row
        if not omit_rowcount:
            self.rowcount = rowcount

    def fetchone(self) -> dict[str, object] | None:
        return self._row


class ReselectRepresentativeReturningConnection:
    def __init__(
        self,
        *,
        row: dict[str, object] | None,
        rowcount: object = 1,
        omit_rowcount: bool = False,
    ) -> None:
        self.row = row
        self.rowcount = rowcount
        self.omit_rowcount = omit_rowcount
        self.reselect_sql = ""
        self.params: object = None
        self.statements: list[tuple[str, object]] = []

    def execute(self, sql: str, params: object = None) -> ReselectRepresentativeReturningCursor:
        self.statements.append((sql, params))
        if "WITH representative_edge AS" in sql and "UPDATE news_items AS items" in sql:
            self.reselect_sql = sql
            self.params = params
            return ReselectRepresentativeReturningCursor(
                row=self.row,
                rowcount=self.rowcount,
                omit_rowcount=self.omit_rowcount,
            )
        return ReselectRepresentativeReturningCursor(row=None, rowcount=0)


class ReselectRepresentativeReturningCursor:
    def __init__(
        self,
        *,
        row: dict[str, object] | None,
        rowcount: object = 1,
        omit_rowcount: bool = False,
    ) -> None:
        self._row = row
        if not omit_rowcount:
            self.rowcount = rowcount

    def fetchone(self) -> dict[str, object] | None:
        return self._row


class RemapEdgesReturningConnection:
    def __init__(
        self,
        *,
        rows: list[dict[str, object]],
        rowcount: object = 1,
        omit_rowcount: bool = False,
        candidate_rows: list[dict[str, object]] | None = None,
    ) -> None:
        self.rows = rows
        self.rowcount = rowcount
        self.omit_rowcount = omit_rowcount
        self.candidate_rows = candidate_rows or []
        self.remap_sql = ""
        self.statements: list[tuple[str, object]] = []

    def execute(self, sql: str, params: object = None) -> RemapEdgesReturningCursor:
        self.statements.append((sql, params))
        if "SELECT pg_advisory_xact_lock" in sql:
            return RemapEdgesReturningCursor(rows=[], rowcount=0)
        if "WITH ranked_edges AS" in sql:
            return RemapEdgesReturningCursor(rows=self.candidate_rows, rowcount=len(self.candidate_rows))
        if "WITH remapped AS" in sql and "UPDATE news_item_observation_edges AS edges" in sql:
            self.remap_sql = sql
            return RemapEdgesReturningCursor(
                rows=self.rows,
                rowcount=self.rowcount,
                omit_rowcount=self.omit_rowcount,
            )
        return RemapEdgesReturningCursor(rows=[], rowcount=0)


class RemapEdgesReturningCursor:
    def __init__(
        self,
        *,
        rows: list[dict[str, object]],
        rowcount: object = 1,
        omit_rowcount: bool = False,
    ) -> None:
        self._rows = rows
        if not omit_rowcount:
            self.rowcount = rowcount

    def fetchone(self) -> dict[str, object] | None:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[dict[str, object]]:
        return list(self._rows)


class ClaimUnprocessedItemsConnection:
    def __init__(
        self,
        *,
        rows: list[dict[str, object]],
        rowcount: object = 1,
        omit_rowcount: bool = False,
    ) -> None:
        self.rows = rows
        self.rowcount = rowcount
        self.omit_rowcount = omit_rowcount
        self.claim_sql = ""
        self.params: object = None
        self.statements: list[tuple[str, object]] = []

    def execute(self, sql: str, params: object = None) -> ClaimUnprocessedItemsCursor:
        self.statements.append((sql, params))
        if "WITH picked AS" in sql and "UPDATE news_items AS items" in sql:
            self.claim_sql = sql
            self.params = params
            return ClaimUnprocessedItemsCursor(
                rows=self.rows,
                rowcount=self.rowcount,
                omit_rowcount=self.omit_rowcount,
            )
        return ClaimUnprocessedItemsCursor(rows=[], rowcount=0)


class ClaimUnprocessedItemsCursor:
    def __init__(
        self,
        *,
        rows: list[dict[str, object]],
        rowcount: object = 1,
        omit_rowcount: bool = False,
    ) -> None:
        self._rows = rows
        if not omit_rowcount:
            self.rowcount = rowcount

    def fetchall(self) -> list[dict[str, object]]:
        return list(self._rows)


class ClaimDueSourcesConnection:
    def __init__(
        self,
        *,
        rows: list[dict[str, object]],
        rowcount: object = 1,
        omit_rowcount: bool = False,
    ) -> None:
        self.rows = rows
        self.rowcount = rowcount
        self.omit_rowcount = omit_rowcount
        self.params: object = None
        self.statements: list[tuple[str, object]] = []

    def execute(self, sql: str, params: object = None) -> ClaimDueSourcesCursor:
        self.params = params
        self.statements.append((sql, params))
        return ClaimDueSourcesCursor(
            rows=self.rows,
            rowcount=self.rowcount,
            omit_rowcount=self.omit_rowcount,
        )


class ClaimDueSourcesCursor:
    def __init__(
        self,
        *,
        rows: list[dict[str, object]],
        rowcount: object = 1,
        omit_rowcount: bool = False,
    ) -> None:
        self._rows = rows
        if not omit_rowcount:
            self.rowcount = rowcount

    def fetchall(self) -> list[dict[str, object]]:
        return list(self._rows)


class StartFetchRunConnection:
    def __init__(
        self,
        *,
        insert_rowcount: object = 1,
        source_rowcount: object = 1,
        insert_omit_rowcount: bool = False,
        source_omit_rowcount: bool = False,
    ) -> None:
        self.insert_rowcount = insert_rowcount
        self.source_rowcount = source_rowcount
        self.insert_omit_rowcount = insert_omit_rowcount
        self.source_omit_rowcount = source_omit_rowcount
        self.statements: list[tuple[str, object]] = []

    def execute(self, sql: str, params: object = None) -> StartFetchRunCursor:
        self.statements.append((sql, params))
        if "INSERT INTO news_fetch_runs" in sql:
            return StartFetchRunCursor(
                rowcount=self.insert_rowcount,
                omit_rowcount=self.insert_omit_rowcount,
            )
        if "UPDATE news_sources" in sql:
            return StartFetchRunCursor(
                rowcount=self.source_rowcount,
                omit_rowcount=self.source_omit_rowcount,
            )
        return StartFetchRunCursor(rowcount=0)


class StartFetchRunCursor:
    def __init__(self, *, rowcount: object = 1, omit_rowcount: bool = False) -> None:
        if not omit_rowcount:
            self.rowcount = rowcount


class FinishFetchRunConnection:
    def __init__(
        self,
        *,
        row: dict[str, object] | None,
        rowcount: object = 1,
        omit_rowcount: bool = False,
        source_rowcount: object = 1,
        source_omit_rowcount: bool = False,
    ) -> None:
        self.row = row
        self.rowcount = rowcount
        self.omit_rowcount = omit_rowcount
        self.source_rowcount = source_rowcount
        self.source_omit_rowcount = source_omit_rowcount
        self.statements: list[tuple[str, object]] = []

    def execute(self, sql: str, params: object = None) -> FinishFetchRunCursor:
        self.statements.append((sql, params))
        if "UPDATE news_fetch_runs" in sql:
            return FinishFetchRunCursor(
                row=self.row,
                rowcount=self.rowcount,
                omit_rowcount=self.omit_rowcount,
            )
        if "UPDATE news_sources" in sql:
            return FinishFetchRunCursor(
                row=None,
                rowcount=self.source_rowcount,
                omit_rowcount=self.source_omit_rowcount,
            )
        return FinishFetchRunCursor(row=None, rowcount=0)


class FinishFetchRunCursor:
    def __init__(
        self,
        *,
        row: dict[str, object] | None,
        rowcount: object = 1,
        omit_rowcount: bool = False,
    ) -> None:
        self._row = row
        if not omit_rowcount:
            self.rowcount = rowcount

    def fetchone(self) -> dict[str, object] | None:
        return self._row


class DeleteReturningConnection:
    def __init__(
        self,
        *,
        rows: list[dict[str, object]],
        rowcount: object = 1,
        omit_rowcount: bool = False,
    ) -> None:
        self.rows = rows
        self.rowcount = rowcount
        self.omit_rowcount = omit_rowcount
        self.statements: list[tuple[str, object]] = []

    def execute(self, sql: str, params: object = None) -> DeleteReturningCursor:
        self.statements.append((sql, params))
        return DeleteReturningCursor(rows=self.rows, rowcount=self.rowcount, omit_rowcount=self.omit_rowcount)


class DeleteReturningCursor:
    def __init__(
        self,
        *,
        rows: list[dict[str, object]],
        rowcount: object = 1,
        omit_rowcount: bool = False,
    ) -> None:
        self._rows = rows
        if not omit_rowcount:
            self.rowcount = rowcount

    def fetchone(self) -> dict[str, object] | None:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[dict[str, object]]:
        return list(self._rows)


class PageRowReturningConnection:
    def __init__(
        self,
        *,
        returned_row: dict[str, object] | None,
        rowcount: object = 1,
        omit_rowcount: bool = False,
    ) -> None:
        self.returned_row = returned_row
        self.rowcount = rowcount
        self.omit_rowcount = omit_rowcount
        self.statements: list[tuple[str, object]] = []

    def execute(self, sql: str, params: object = None) -> PageRowReturningCursor:
        self.statements.append((sql, params))
        if "INSERT INTO news_page_rows" in sql:
            return PageRowReturningCursor(
                row=self.returned_row,
                rowcount=self.rowcount,
                omit_rowcount=self.omit_rowcount,
            )
        return PageRowReturningCursor(row=None, rows=[], rowcount=0)


class PageRowReturningCursor:
    def __init__(
        self,
        *,
        row: dict[str, object] | None,
        rows: list[dict[str, object]] | None = None,
        rowcount: object = 1,
        omit_rowcount: bool = False,
    ) -> None:
        self._row = row
        self._rows = rows or []
        if not omit_rowcount:
            self.rowcount = rowcount

    def fetchone(self) -> dict[str, object] | None:
        return self._row

    def fetchall(self) -> list[dict[str, object]]:
        return list(self._rows)


class AgentReturningConnection:
    def __init__(
        self,
        *,
        row: dict[str, object] | None,
        rowcount: object = 1,
        omit_rowcount: bool = False,
    ) -> None:
        self.row = row
        self.rowcount = rowcount
        self.omit_rowcount = omit_rowcount
        self.write_sql = ""
        self.statements: list[tuple[str, object]] = []

    def execute(self, sql: str, params: object = None) -> AgentReturningCursor:
        self.write_sql = sql
        self.statements.append((sql, params))
        return AgentReturningCursor(
            row=self.row,
            rowcount=self.rowcount,
            omit_rowcount=self.omit_rowcount,
        )


class AgentReturningCursor:
    def __init__(
        self,
        *,
        row: dict[str, object] | None,
        rowcount: object = 1,
        omit_rowcount: bool = False,
    ) -> None:
        self._row = row
        if not omit_rowcount:
            self.rowcount = rowcount

    def fetchone(self) -> dict[str, object] | None:
        return self._row


class CapturingConnectionTransaction:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def __enter__(self) -> None:
        self.events.append("begin")

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.events.append("rollback" if exc_type else "commit")


def _start_fetch_run(repo: NewsSourceRepository) -> str:
    return repo.start_fetch_run(
        source_id="source-1",
        started_at_ms=1_000,
    )


def _upsert_source(repo: NewsSourceRepository) -> dict[str, Any]:
    return repo.upsert_source(
        source_id="source-1",
        provider_type="rss",
        feed_url="https://example.com/feed.xml",
        source_domain="example.com",
        source_name="Example",
        now_ms=1_000,
    )


def _upsert_provider_item(repo: NewsSourceRepository) -> dict[str, Any]:
    return repo.upsert_provider_item(
        source_id="source-1",
        fetch_run_id="run-1",
        source_item_key="item-1",
        canonical_url="https://example.com/news/1",
        payload_hash="payload-1",
        raw_payload={"id": "article-1", "provider_signal": {"status": "ready"}},
        fetched_at_ms=1_000,
    )


def _upsert_canonical_news_item(repo: NewsItemRepository) -> dict[str, Any]:
    def refresh_summary(*, news_item_id: str, now_ms: int) -> dict[str, Any]:
        return {
            "news_item_id": news_item_id,
            "canonical_item_key": "url:https://example.com/news/1",
            "updated_at_ms": now_ms,
        }

    repo._refresh_news_item_observation_summary = refresh_summary  # type: ignore[method-assign]
    return repo.upsert_canonical_news_item(
        provider_item_id="provider-item-1",
        canonical_url="https://example.com/news/1",
        title="Example headline",
        summary="Example summary",
        body_text="Example body",
        fetched_at_ms=1_000,
        content_hash="content-1",
        title_fingerprint="example headline",
        now_ms=1_100,
        provider_payload_status="ready",
    )


def _material_duplicate_candidate_row() -> dict[str, Any]:
    return {
        "news_item_id": "news-old",
        "canonical_item_key": "material:old",
        "dedup_key_kind": "material_title",
        "dedup_key_confidence": "medium",
        "url_identity_kind": "generic",
        "title": "Bitcoin crashes as billions of longs get liquidated",
        "provider_token_impacts_json": [{"symbol": "BTC"}],
        "published_at_ms": 1_200_000,
        "provider_payload_status": "ready",
    }


def _current_policy_material_row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "provider_type": "opennews",
        "source_id": "opennews-news",
        "news_item_id": "news-1",
        "title": "Bitcoin crashes as billions of longs get liquidated",
        "published_at_ms": 1_200_000,
        "provider_token_impacts_json": [{"symbol": "BTC"}],
    }
    row.update(overrides)
    return row


def _valid_news_item_aggregate_row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "duplicate_observation_count": 1,
        "source_ids_json": ["source-1"],
        "source_domains_json": ["example.com"],
        "provider_article_keys_json": ["opennews:article-1"],
    }
    row.update(overrides)
    return row


def _remap_material_duplicate_edges(repo: NewsItemRepository) -> list[str]:
    return repo._remap_material_duplicate_edges_to_news_item(
        source_id="opennews-news",
        news_item_id="news-1",
        canonical_item_key="url:https://example.com/news/1",
        title="Bitcoin crashes as billions of longs get liquidated",
        published_at_ms=1_200_000,
        provider_token_impacts=[{"symbol": "BTC"}],
        now_ms=1_300_000,
    )


def _news_story_agent_run_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "run_id": "story-run-1",
        "story_brief_key": "story-brief-1",
        "story_key": "story:btc",
        "story_identity_version": NEWS_STORY_IDENTITY_VERSION,
        "representative_news_item_id": "news-1",
        "member_news_item_ids_json": ["news-1", "news-2"],
        "provider": "openai",
        "model": "gpt-test",
        "backend": "litellm_sdk",
        "execution_trace_id": "trace-story-1",
        "workflow_name": "news_story_brief",
        "agent_name": "news_story_brief",
        "lane": "news.story_brief",
        "artifact_version_hash": "artifact-story-1",
        "prompt_version": "prompt-story-v1",
        "schema_version": "schema-story-v1",
        "validator_version": "validator-story-v1",
        "guardrail_version": "guardrail-story-v1",
        "input_hash": "input-story-1",
        "output_hash": "output-story-1",
        "execution_started": True,
        "status": "completed",
        "outcome": "ready",
        "request_json": {"messages": []},
        "response_json": {"summary_zh": "故事摘要"},
        "validation_errors_json": [],
        "trace_metadata_json": {},
        "usage_json": {},
        "latency_ms": 12,
        "started_at_ms": 1_000,
        "finished_at_ms": 1_100,
        "created_at_ms": 1_100,
    }
    payload.update(overrides)
    return payload


def _news_story_agent_brief_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "story_brief_key": "story-brief-1",
        "story_key": "story:btc",
        "story_identity_version": NEWS_STORY_IDENTITY_VERSION,
        "representative_news_item_id": "news-1",
        "member_news_item_ids_json": ["news-1", "news-2"],
        "agent_run_id": "story-run-1",
        "status": "ready",
        "direction": "bullish",
        "decision_class": "high_signal",
        "brief_json": {"summary_zh": "这是一条可发布故事摘要"},
        "input_hash": "input-story-1",
        "artifact_version_hash": "artifact-story-1",
        "prompt_version": "prompt-story-v1",
        "schema_version": "schema-story-v1",
        "validator_version": "validator-story-v1",
        "computed_at_ms": 1_100,
        "created_at_ms": 1_100,
        "updated_at_ms": 1_100,
    }
    payload.update(overrides)
    return payload


def _finish_fetch_run(repo: NewsSourceRepository) -> dict[str, Any]:
    return repo.finish_fetch_run(
        fetch_run_id="run-1",
        source_id="source-1",
        status="success",
        finished_at_ms=1_000,
        fetched_count=1,
        inserted_count=1,
        updated_count=0,
        duplicate_count=0,
    )


def _valid_market_scope() -> NewsMarketScope:
    return NewsMarketScope(
        scope=("crypto",),
        primary="crypto",
        status="classified",
        reason="crypto_evidence",
        basis={"crypto_evidence": ["resolved_crypto_target:cex:BTC"]},
        version=NEWS_MARKET_SCOPE_VERSION,
    )


def _valid_market_scope_payload() -> dict[str, object]:
    return {
        "scope": ["crypto"],
        "primary": "crypto",
        "status": "classified",
        "reason": "crypto_evidence",
        "basis": {"crypto_evidence": ["resolved_crypto_target:cex:BTC"]},
        "version": "news_market_scope_v1",
    }


def _valid_story_identity() -> NewsStoryIdentity:
    return NewsStoryIdentity(
        story_key="news-story:event:exchange-listing:upbit:ctr:btc-usdt:t20613",
        confidence="strong",
        basis={
            "method": "exchange_listing_event_key",
            "subject": "exchange-listing:upbit:ctr:btc-usdt",
        },
        version=NEWS_STORY_IDENTITY_VERSION,
    )


def _valid_story_identity_payload() -> dict[str, object]:
    return {
        "story_key": "news-story:event:exchange-listing:upbit:ctr:btc-usdt:t20613",
        "confidence": "strong",
        "basis": {
            "method": "exchange_listing_event_key",
            "subject": "exchange-listing:upbit:ctr:btc-usdt",
        },
        "version": "news_story_identity_v2",
    }


def _valid_agent_admission() -> NewsItemAgentAdmission:
    return NewsItemAgentAdmission(
        eligible=True,
        status="eligible",
        reason="eligible",
        representative_news_item_id="news-1",
        basis={"market_scope": ["crypto"]},
        version=NEWS_ITEM_AGENT_ADMISSION_VERSION,
    )


def _valid_agent_admission_payload() -> dict[str, object]:
    return {
        "eligible": True,
        "status": "eligible",
        "reason": "eligible",
        "representative_news_item_id": "news-1",
        "basis": {"market_scope": ["crypto"]},
        "version": "news_item_agent_admission_v1",
    }


def _valid_news_page_row() -> dict[str, object]:
    return {
        "row_id": "row-news-1",
        "news_item_id": "news-1",
        "representative_news_item_id": "news-1",
        "story_key": "story:news-1",
        "story": {
            "member_news_item_ids": ["news-1"],
            "member_count": 1,
            "source_ids": ["source-1"],
        },
        "latest_at_ms": 1_779_000_000_000,
        "lifecycle_status": "ready",
        "headline": "Bitcoin ETF flows jump",
        "summary": "ETF flow update",
        "source_domain": "example.com",
        "canonical_url": "https://example.com/news-1",
        "token_lanes": [],
        "fact_lanes": [],
        "content_class": "market_moving",
        "content_tags": ["etf"],
        "content_classification": {"status": "classified"},
        "source": {"source_id": "source-1", "source_domain": "example.com"},
        "signal": {"display_signal": "neutral"},
        "provider_rating": {},
        "token_impacts": [],
        "agent_brief": {"status": "pending"},
        "agent_status": "pending",
        "agent_brief_computed_at_ms": None,
        "computed_at_ms": 1_779_000_000_000,
        "projection_version": "news_page_rows_v5",
        "canonical_item_key": "news-1",
        "duplicate_count": 0,
        "source_ids_json": [],
        "source_domains_json": [],
        "provider_article_keys_json": [],
        "market_scope": {"primary": "crypto"},
        "macro_event_flow": None,
        "agent_admission": _valid_agent_admission_payload(),
        "agent_admission_status": "eligible",
        "agent_admission_reason": "eligible",
        "agent_representative_news_item_id": "news-1",
    }


def _valid_news_item_detail_base_row() -> dict[str, object]:
    return {
        "item": {
            "news_item_id": "news-1",
            "source_id": "source-1",
            "source_domain": "raw.example",
            "canonical_url": "https://raw.example/news-1",
            "title": "Raw title",
            "summary": "Raw summary",
            "language": "en",
            "published_at_ms": 1_779_000_000_000,
            "fetched_at_ms": 1_779_000_000_100,
            "lifecycle_status": "processed",
            "content_class": "raw_low_signal",
            "story_key": "raw-story",
            "story_identity_json": {"story_key": "raw-story"},
            "market_scope_json": {"primary": "raw"},
            "agent_admission_status": "raw_status",
            "agent_admission_reason": "raw_reason",
            "agent_admission_json": {"status": "raw_status"},
            "agent_representative_news_item_id": "raw-agent-news",
            "agent_admission_computed_at_ms": 1_779_000_000_200,
        },
        "source": {
            "source_id": "source-1",
            "provider_type": "opennews",
            "source_domain": "raw.example",
            "source_name": "Raw Source",
            "source_role": "news",
            "trust_tier": "standard",
            "enabled": True,
        },
        "provider_item": {
            "source_id": "source-1",
            "canonical_url": "https://raw.example/news-1",
            "provider_payload_status": "ok",
            "provider_published_at_ms": 1_779_000_000_000,
            "provider_observed_at_ms": 1_779_000_000_100,
        },
        "fetch_run": None,
        "agent_brief": None,
        "agent_run": None,
        "entities": [],
        "token_mentions": [],
        "fact_candidates": [],
    }


def _valid_news_item_detail_page_row() -> dict[str, object]:
    return {
        "row_id": "row-news-1",
        "representative_news_item_id": "projected-news-1",
        "story_key": "projected-story",
        "story": {
            "story_key": "projected-story",
            "member_news_item_ids": ["news-1"],
        },
        "latest_at_ms": 1_779_000_000_000,
        "lifecycle_status": "ready",
        "token_lanes": [],
        "fact_lanes": [],
        "signal": {"display_signal": {"direction": "neutral"}},
        "provider_rating": {"status": "rated"},
        "token_impacts": [],
        "content_class": "market_moving",
        "content_tags": ["etf"],
        "content_classification": {"status": "classified"},
        "page_source": {"source_id": "source-1"},
        "page_agent_brief": {"status": "pending"},
        "agent_status": "pending",
        "agent_brief_computed_at_ms": None,
        "market_scope": {"primary": "crypto"},
        "agent_admission_status": "eligible",
        "agent_admission_reason": "eligible",
        "agent_admission": _valid_agent_admission_payload(),
        "agent_representative_news_item_id": "projected-agent-news-1",
        "computed_at_ms": 1_779_000_000_500,
        "projection_version": "news_page_rows_v5",
    }


def _valid_page_projection_loader_row() -> dict[str, object]:
    return {
        "item": _valid_news_item_detail_base_row()["item"],
        "token_mentions": [],
        "fact_candidates": [],
    }


def _valid_agent_admission_context_loader_row() -> dict[str, object]:
    return {
        "item": _valid_news_item_detail_base_row()["item"],
        "entities": [],
        "token_mentions": [],
        "fact_candidates": [],
        "exact_duplicate_candidates": [],
        "story_candidates": [],
    }


def _valid_story_brief_target_row() -> dict[str, object]:
    return {
        "story_key": "story:news-1",
        "current_brief": None,
        "latest_run": None,
        "source_updated_at_ms": 1_779_000_000_500,
        "item": {
            "news_item_id": "news-1",
            "title": "Coinbase lists NEWX",
            "summary": "Trading starts today",
            "source_domain": "example.test",
            "published_at_ms": 1_779_000_000_000,
            "source_ids_json": ["source-1"],
            "source_domains_json": ["example.test"],
            "provider_article_keys_json": ["opennews:1"],
            "story_identity_json": _valid_story_identity_payload(),
            "story_identity_version": NEWS_STORY_IDENTITY_VERSION,
            "market_scope_json": _valid_market_scope_payload(),
            "agent_admission_json": _valid_agent_admission_payload(),
        },
        "entities": [],
        "token_mentions": [],
        "fact_candidates": [],
    }


def _valid_news_dedup_diagnostics_row() -> dict[str, object]:
    return {
        "raw_observation_count": 1,
        "canonical_item_count": 1,
        "observation_edge_count": 1,
        "enabled_serving_row_count": 1,
        "disabled_serving_row_count": 0,
        "enabled_exact_content_visible_duplicate_excess": 0,
        "top_visible_content_duplicate_groups": [],
        "top_visible_canonical_duplicate_groups": [],
        "material_title_duplicate_groups": {"groups": 0, "rows": 0, "duplicate_rows": 0, "top_groups": []},
        "case_insensitive_url_duplicate_groups": {"groups": 0, "rows": 0, "duplicate_rows": 0, "top_groups": []},
        "preview_or_generic_url_rows": {"rows": 0},
        "source_sync_diagnostics": [],
    }


def _valid_news_page_read_row() -> dict[str, object]:
    return {
        "row_id": "row-news-1",
        "news_item_id": "news-1",
        "representative_news_item_id": "news-1",
        "story_key": "story:news-1",
        "story": {
            "story_key": "story:news-1",
            "member_news_item_ids": ["news-1"],
        },
        "latest_at_ms": 1_779_000_000_000,
        "lifecycle_status": "ready",
        "headline": "Bitcoin ETF flows jump",
        "summary": "ETF flow update",
        "source_domain": "example.com",
        "canonical_url": "https://example.com/news-1",
        "duplicate_count": 1,
        "source_ids": ["source-1"],
        "source_domains": ["example.com"],
        "token_lanes": [],
        "fact_lanes": [],
        "signal": {"display_signal": {"direction": "neutral"}},
        "provider_rating": {"status": "rated"},
        "token_impacts": [],
        "content_class": "market_moving",
        "content_tags": ["etf"],
        "content_classification": {"status": "classified"},
        "source": {"source_id": "source-1", "source_domain": "example.com"},
        "agent_brief": {"status": "pending"},
        "agent_status": "pending",
        "agent_brief_computed_at_ms": None,
        "market_scope": {"primary": "crypto"},
        "agent_admission_status": "eligible",
        "agent_admission_reason": "eligible",
        "agent_admission": _valid_agent_admission_payload(),
        "agent_representative_news_item_id": "news-1",
        "computed_at_ms": 1_779_000_000_500,
        "projection_version": "news_page_rows_v5",
    }


class CapturingCursor:
    rowcount = 1

    def fetchone(self) -> dict[str, Any]:
        return {"news_item_id": "news-old", "has_edges": False}

    def fetchall(self) -> list[dict[str, Any]]:
        return []


class TransactionRecordingConnection:
    def __init__(self) -> None:
        self.events: list[str] = []

    def execute(self, sql: str, params: object = None) -> CapturingCursor:
        self.events.append("execute")
        raise RuntimeError("stop after transaction entry")

    def transaction(self) -> TransactionRecorder:
        return TransactionRecorder(self.events)


class TransactionRecorder:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def __enter__(self) -> None:
        self.events.append("begin")

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.events.append("rollback" if exc_type else "commit")
