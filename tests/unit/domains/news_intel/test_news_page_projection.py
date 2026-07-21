from __future__ import annotations

from typing import Any

import pytest

from parallax.domains.news_intel._constants import NEWS_PAGE_PROJECTION_VERSION
from parallax.domains.news_intel.services.news_page_projection import _page_signal
from parallax.domains.news_intel.services.news_page_projection import build_news_page_row as _build_news_page_row
from parallax.domains.news_intel.types.news_page_search import build_news_page_search_text


def build_news_page_row(
    *,
    item: dict[str, Any],
    token_mentions: list[dict[str, Any]],
    fact_candidates: list[dict[str, Any]],
    computed_at_ms: int,
    story: dict[str, Any] | None = None,
    agent_brief: dict[str, Any] | None = None,
) -> dict[str, Any]:
    projection_item = _with_required_projection_context(item)
    return _build_news_page_row(
        item=projection_item,
        token_mentions=token_mentions,
        fact_candidates=fact_candidates,
        story=story or _story_for_item(projection_item),
        agent_brief=agent_brief,
        computed_at_ms=computed_at_ms,
    )


def _story_for_item(item: dict[str, Any]) -> dict[str, Any]:
    news_item_id = str(item["news_item_id"])
    source_domain = str(item.get("source_domain") or "example.test")
    return {
        "story_key": str(item.get("story_key") or f"story:{news_item_id}"),
        "representative_news_item_id": news_item_id,
        "member_news_item_ids": [news_item_id],
        "member_count": 1,
        "source_domains": [source_domain],
    }


def _base_projection_item() -> dict[str, Any]:
    return {
        "news_item_id": "news-1",
        "title": "Coinbase lists NEWX",
        "summary": "Trading starts today",
        "source_domain": "example.test",
        "published_at_ms": 1000,
        "market_scope_json": {
            "scope": ["crypto"],
            "primary": "crypto",
            "status": "classified",
            "reason": "crypto_subject",
            "basis": {"subject": "exchange_listing"},
            "version": "test_news_market_scope_v1",
        },
        "agent_admission_status": "eligible",
        "agent_admission_reason": "ready_market_driver",
        "agent_admission_json": {
            "eligible": True,
            "status": "eligible",
            "reason": "ready_market_driver",
            "representative_news_item_id": "news-1",
            "basis": {"market_scope": ["crypto"]},
            "version": "test_news_item_agent_admission_v1",
        },
        "agent_representative_news_item_id": "news-1",
    }


def _with_required_projection_context(item: dict[str, Any]) -> dict[str, Any]:
    projection_item = dict(item)
    news_item_id = str(projection_item["news_item_id"])
    admission = projection_item.get("agent_admission_json")
    admission_payload = dict(admission) if isinstance(admission, dict) else {}
    status = str(projection_item.get("agent_admission_status") or admission_payload.get("status") or "eligible")
    reason = str(
        projection_item.get("agent_admission_reason") or admission_payload.get("reason") or "unit_test_market_driver"
    )
    representative_news_item_id = str(
        projection_item.get("agent_representative_news_item_id")
        or admission_payload.get("representative_news_item_id")
        or news_item_id
    )
    projection_item.setdefault(
        "market_scope_json",
        {
            "scope": ["crypto"],
            "primary": "crypto",
            "status": "classified",
            "reason": "unit_test_crypto_subject",
            "basis": {"subject": "unit_test"},
            "version": "test_news_market_scope_v1",
        },
    )
    projection_item.setdefault("agent_admission_status", status)
    projection_item.setdefault("agent_admission_reason", reason)
    projection_item.setdefault("agent_representative_news_item_id", representative_news_item_id)
    projection_item.setdefault("content_class", "market_moving")
    projection_item.setdefault("content_tags_json", [])
    projection_item.setdefault("content_classification_json", {})
    projection_item.setdefault("source_quality_status", "healthy")
    projection_item.setdefault("canonical_item_key", f"canonical-url:https://example.test/{news_item_id}")
    projection_item.setdefault(
        "agent_admission_json",
        {
            "eligible": status in {"eligible", "eligible_refresh"},
            "status": status,
            "reason": reason,
            "representative_news_item_id": representative_news_item_id,
            "basis": {"market_scope": ["crypto"]},
            "version": "test_news_item_agent_admission_v1",
        },
    )
    return projection_item


def test_build_news_page_row_uses_persisted_published_time_for_latest_at() -> None:
    row = build_news_page_row(
        item={
            "news_item_id": "news-1",
            "title": "Coinbase lists NEWX",
            "summary": "Trading starts today",
            "source_domain": "example.test",
            "published_at_ms": 1000,
            "fetched_at_ms": 3000,
        },
        token_mentions=[],
        fact_candidates=[],
        computed_at_ms=5000,
    )

    assert row["latest_at_ms"] == 1000


def test_build_news_page_row_copies_canonical_item_key() -> None:
    row = build_news_page_row(
        item={
            "news_item_id": "news-1",
            "title": "Coinbase lists NEWX",
            "summary": "Trading starts today",
            "source_domain": "example.test",
            "canonical_url": "https://example.test/a",
            "canonical_item_key": "canonical-url:https://example.test/a",
            "published_at_ms": 1000,
        },
        token_mentions=[],
        fact_candidates=[],
        computed_at_ms=5000,
    )

    assert row["canonical_item_key"] == "canonical-url:https://example.test/a"


@pytest.mark.parametrize("published_at_ms", [True, "1000", 1000.5, 0])
def test_build_news_page_row_rejects_malformed_published_at_without_int_repair(
    published_at_ms: object,
) -> None:
    item = _base_projection_item()
    item["published_at_ms"] = published_at_ms

    with pytest.raises(ValueError, match="news_page_projection_published_at_required:news-1"):
        build_news_page_row(
            item=item,
            token_mentions=[],
            fact_candidates=[],
            computed_at_ms=5000,
        )


@pytest.mark.parametrize("member_count", [True, "2", 2.5, 0])
def test_story_payload_rejects_malformed_member_count_without_int_repair(member_count: object) -> None:
    story = {
        "story_key": "story:news-1",
        "representative_news_item_id": "news-1",
        "member_news_item_ids": ["news-1"],
        "member_count": member_count,
        "source_domains": ["example.test"],
    }

    with pytest.raises(ValueError, match="news_page_projection_story_member_count_required:news-1"):
        build_news_page_row(
            item=_base_projection_item(),
            token_mentions=[],
            fact_candidates=[],
            story=story,
            computed_at_ms=5000,
        )


@pytest.mark.parametrize("computed_at_ms", [True, "5000", 5000.5, 0])
def test_build_news_page_row_rejects_malformed_computed_at_without_int_repair(
    computed_at_ms: object,
) -> None:
    with pytest.raises(ValueError, match="news_page_projection_computed_at_ms_required:news-1"):
        build_news_page_row(
            item=_base_projection_item(),
            token_mentions=[],
            fact_candidates=[],
            computed_at_ms=computed_at_ms,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("computed_at_ms", [True, "3000", 3000.5, 0])
def test_build_news_page_row_rejects_malformed_agent_brief_computed_at_without_int_repair(
    computed_at_ms: object,
) -> None:
    with pytest.raises(ValueError, match="news_page_projection_agent_brief_computed_at_ms_required:news-1"):
        build_news_page_row(
            item=_base_projection_item(),
            token_mentions=[],
            fact_candidates=[],
            agent_brief={
                "status": "ready",
                "direction": "bullish",
                "decision_class": "driver",
                "brief_json": {"summary_zh": "SOL ETF 申请提升关注。"},
                "computed_at_ms": computed_at_ms,
            },
            computed_at_ms=5000,
        )


def test_news_page_search_text_does_not_restore_from_legacy_alias_fields() -> None:
    search_text = build_news_page_search_text(
        {
            "headline": "Current headline",
            "summary": "Current summary",
            "source_domain": "current.example",
            "source_json": {},
            "source": {"source_id": "legacy-source", "source_name": "Legacy Source"},
            "source_ids_json": [],
            "source_ids": ["legacy-source-id"],
            "source_domains_json": [],
            "source_domains": ["legacy.example"],
            "token_lanes_json": [],
            "token_lanes": [{"symbol": "OLD", "target_id": "asset:old"}],
            "fact_lanes_json": [],
            "fact_lanes": [{"claim": "legacy claim", "event_type": "legacy_event"}],
        }
    )

    assert "Current headline" in search_text
    assert "current.example" in search_text
    assert "legacy-source" not in search_text
    assert "legacy-source-id" not in search_text
    assert "legacy.example" not in search_text
    assert "asset:old" not in search_text
    assert "legacy claim" not in search_text


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("source_json", "example.test"),
        ("source_ids_json", {"source_id": "source-1"}),
        ("source_domains_json", "example.test"),
        ("token_lanes_json", {"symbol": "BTC"}),
        ("token_lanes_json", ["BTC"]),
        ("fact_lanes_json", {"claim": "ETF flow"}),
        ("fact_lanes_json", ["ETF flow"]),
    ],
)
def test_news_page_search_text_rejects_malformed_present_projection_fields(
    field_name: str,
    value: object,
) -> None:
    row: dict[str, Any] = {
        "headline": "Current headline",
        "summary": "Current summary",
        "source_domain": "current.example",
        "source_json": {},
        "source_ids_json": [],
        "source_domains_json": [],
        "token_lanes_json": [],
        "fact_lanes_json": [],
    }
    row[field_name] = value

    with pytest.raises(ValueError, match=f"news_page_search_{field_name}_required"):
        build_news_page_search_text(row)


@pytest.mark.parametrize(
    ("field_name", "error"),
    [
        ("market_scope_json", "news_page_projection_item_market_scope_json_required:news-1"),
        ("canonical_item_key", "news_page_projection_item_canonical_item_key_required:news-1"),
        ("agent_admission_json", "news_page_projection_item_agent_admission_json_required:news-1"),
        ("agent_admission_status", "news_page_projection_item_agent_admission_status_required:news-1"),
        ("agent_admission_reason", "news_page_projection_item_agent_admission_reason_required:news-1"),
        (
            "agent_representative_news_item_id",
            "news_page_projection_item_agent_representative_news_item_id_required:news-1",
        ),
    ],
)
def test_build_news_page_row_rejects_missing_required_item_projection_context(
    field_name: str,
    error: str,
) -> None:
    item = _with_required_projection_context(_base_projection_item())
    item.pop(field_name)

    with pytest.raises(ValueError, match=error):
        _build_news_page_row(
            item=item,
            token_mentions=[],
            fact_candidates=[],
            story=_story_for_item(item),
            computed_at_ms=5000,
        )


@pytest.mark.parametrize(
    ("field_name", "value", "error"),
    [
        ("market_scope_json", ["crypto"], "news_page_projection_item_market_scope_json_required:news-1"),
        (
            "agent_admission_json",
            {"status": "eligible", "reason": "ready_market_driver"},
            "news_page_projection_agent_admission_representative_news_item_id_required:news-1",
        ),
        ("agent_admission_status", "needs_review", "news_page_projection_agent_admission_status_mismatch:news-1"),
        (
            "agent_representative_news_item_id",
            "news-other",
            "news_page_projection_agent_admission_representative_news_item_id_mismatch:news-1",
        ),
    ],
)
def test_build_news_page_row_rejects_malformed_required_item_projection_context(
    field_name: str,
    value: Any,
    error: str,
) -> None:
    item = _with_required_projection_context(_base_projection_item())
    item[field_name] = value

    with pytest.raises(ValueError, match=error):
        _build_news_page_row(
            item=item,
            token_mentions=[],
            fact_candidates=[],
            story=_story_for_item(item),
            computed_at_ms=5000,
        )


@pytest.mark.parametrize(
    ("field_name", "error"),
    [
        ("similar_story", "news_page_projection_agent_admission_similar_story_required:news-1"),
        ("exact_duplicate", "news_page_projection_agent_admission_exact_duplicate_required:news-1"),
    ],
)
def test_build_news_page_row_rejects_malformed_agent_admission_basis_matches(
    field_name: str,
    error: str,
) -> None:
    item = _with_required_projection_context(_base_projection_item())
    item["agent_admission_json"] = {
        **item["agent_admission_json"],
        "basis": {
            "market_scope": ["crypto"],
            field_name: ["malformed"],
        },
    }

    with pytest.raises(ValueError, match=error):
        _build_news_page_row(
            item=item,
            token_mentions=[],
            fact_candidates=[],
            story=_story_for_item(item),
            computed_at_ms=5000,
        )


def test_build_news_page_row_requires_canonical_published_time() -> None:
    with pytest.raises(ValueError, match="news_page_projection_published_at_required:news-missing-time"):
        build_news_page_row(
            item={
                "news_item_id": "news-missing-time",
                "title": "Malformed item",
                "summary": "",
                "source_domain": "example.test",
                "fetched_at_ms": 3000,
            },
            token_mentions=[],
            fact_candidates=[],
            computed_at_ms=5000,
        )


def test_build_news_page_row_requires_story_payload_after_story_agent_hard_cut() -> None:
    with pytest.raises(ValueError, match="news_page_projection_story_required:news-1"):
        _build_news_page_row(
            item={
                "news_item_id": "news-1",
                "title": "Coinbase lists NEWX",
                "summary": "Trading starts today",
                "source_domain": "example.test",
                "canonical_item_key": "canonical-url:https://example.test/news-1",
                "published_at_ms": 1000,
            },
            token_mentions=[],
            fact_candidates=[],
            computed_at_ms=5000,
        )


def test_build_news_page_row_includes_token_and_fact_lanes() -> None:
    row = build_news_page_row(
        item={
            "news_item_id": "news-1",
            "title": "Coinbase lists NEWX",
            "summary": "Trading starts today",
            "source_id": "example-rss",
            "source_domain": "example.test",
            "canonical_url": "https://example.test/a",
            "published_at_ms": 1000,
            "lifecycle_status": "processed",
        },
        token_mentions=[
            {
                "resolution_status": "unknown_attention",
                "display_symbol": "NEWX",
                "target_id": None,
                "reason_codes_json": ["SYMBOL_NOT_IN_REGISTRY"],
            }
        ],
        fact_candidates=[
            {
                "event_type": "listing",
                "validation_status": "attention",
                "rejection_reasons_json": ["target_identity_not_production_eligible"],
            }
        ],
        computed_at_ms=2000,
    )

    assert row["lifecycle_status"] == "attention"
    assert row["token_lanes"][0]["lane"] == "attention"
    assert row["token_lanes"][0]["reason_codes"] == ["SYMBOL_NOT_IN_REGISTRY"]
    assert row["fact_lanes"][0]["status"] == "attention"
    assert row["representative_news_item_id"] == "news-1"
    assert row["story_key"] == "story:news-1"
    assert row["story"] == {
        "story_key": "story:news-1",
        "representative_news_item_id": "news-1",
        "member_news_item_ids": ["news-1"],
        "member_count": 1,
        "source_domains": ["example.test"],
    }
    assert row["market_scope"]["primary"] == "crypto"
    assert "analysis_admission_status" not in row
    assert "analysis_admission_reason" not in row
    assert "analysis_admission" not in row
    assert "story_id" not in row
    assert row["source"] == {
        "source_id": "example-rss",
        "source_domain": "example.test",
        "coverage_tags": [],
        "source_quality_status": "healthy",
    }
    assert row["projection_version"] == NEWS_PAGE_PROJECTION_VERSION


@pytest.mark.parametrize(
    ("lane_kind", "field_name", "value"),
    [
        ("token", "reason_codes_json", "SYMBOL_NOT_IN_REGISTRY"),
        ("token", "candidate_targets_json", {"target_id": "asset:bad"}),
        ("fact", "rejection_reasons_json", "target_identity_not_production_eligible"),
        ("fact", "affected_targets_json", {"target_id": "asset:bad"}),
    ],
)
def test_build_news_page_row_rejects_malformed_present_lane_lists(
    lane_kind: str,
    field_name: str,
    value: Any,
) -> None:
    token_mentions = [
        {
            "resolution_status": "unknown_attention",
            "display_symbol": "NEWX",
            "reason_codes_json": ["SYMBOL_NOT_IN_REGISTRY"],
            "candidate_targets_json": [],
        }
    ]
    fact_candidates = [
        {
            "event_type": "listing",
            "validation_status": "attention",
            "rejection_reasons_json": ["target_identity_not_production_eligible"],
            "affected_targets_json": [],
        }
    ]
    if lane_kind == "token":
        token_mentions[0][field_name] = value
    else:
        fact_candidates[0][field_name] = value

    with pytest.raises(ValueError, match=f"news_page_projection_{lane_kind}_lane_{field_name}_required"):
        build_news_page_row(
            item={
                "news_item_id": "news-1",
                "title": "Coinbase lists NEWX",
                "summary": "Trading starts today",
                "source_id": "example-rss",
                "source_domain": "example.test",
                "canonical_url": "https://example.test/a",
                "published_at_ms": 1000,
                "lifecycle_status": "processed",
            },
            token_mentions=token_mentions,
            fact_candidates=fact_candidates,
            computed_at_ms=2000,
        )


def test_build_news_page_row_includes_compact_source_classification() -> None:
    row = build_news_page_row(
        item={
            "news_item_id": "news-1",
            "title": "Coinbase lists NEWX",
            "summary": "Trading starts today",
            "source_id": "coinbase-announcements",
            "provider_type": "rss",
            "source_domain": "coinbase.com",
            "source_name": "Coinbase Announcements",
            "source_role": "official_exchange",
            "trust_tier": "official",
            "coverage_tags_json": ["crypto_exchange", "exchange_listing"],
            "source_quality_status": "healthy",
            "canonical_url": "https://coinbase.com/a",
            "published_at_ms": 1000,
        },
        token_mentions=[],
        fact_candidates=[],
        computed_at_ms=2000,
    )

    assert row["source"] == {
        "source_id": "coinbase-announcements",
        "provider_type": "rss",
        "source_domain": "coinbase.com",
        "source_name": "Coinbase Announcements",
        "source_role": "official_exchange",
        "trust_tier": "official",
        "coverage_tags": ["crypto_exchange", "exchange_listing"],
        "source_quality_status": "healthy",
    }


@pytest.mark.parametrize("coverage_tags_json", ["crypto_exchange", {"tag": "crypto_exchange"}])
def test_build_news_page_row_rejects_malformed_present_source_coverage_tags(
    coverage_tags_json: object,
) -> None:
    with pytest.raises(ValueError, match="news_page_projection_item_coverage_tags_json_required:news-1"):
        build_news_page_row(
            item={
                "news_item_id": "news-1",
                "title": "Coinbase lists NEWX",
                "summary": "Trading starts today",
                "source_id": "coinbase-announcements",
                "provider_type": "rss",
                "source_domain": "coinbase.com",
                "source_name": "Coinbase Announcements",
                "source_role": "official_exchange",
                "trust_tier": "official",
                "coverage_tags_json": coverage_tags_json,
                "source_quality_status": "healthy",
                "canonical_url": "https://coinbase.com/a",
                "published_at_ms": 1000,
            },
            token_mentions=[],
            fact_candidates=[],
            computed_at_ms=2000,
        )


def test_build_news_page_row_copies_item_level_content_classification() -> None:
    row = build_news_page_row(
        item={
            "news_item_id": "news-1",
            "title": "SEC delays tokenized stock decision",
            "summary": "The filing remains open.",
            "source_domain": "example.test",
            "canonical_url": "https://example.test/sec",
            "published_at_ms": 1000,
            "content_class": "regulation",
            "content_tags_json": ("sec", "tokenized_stocks"),
            "content_classification_json": {
                "policy_version": "news_content_classification_v1",
                "matched_rules": ["regulatory_body"],
                "none_value": None,
            },
        },
        token_mentions=[],
        fact_candidates=[],
        computed_at_ms=2000,
    )

    assert row["content_class"] == "regulation"
    assert row["content_tags"] == ["sec", "tokenized_stocks"]
    assert row["content_classification"] == {
        "policy_version": "news_content_classification_v1",
        "matched_rules": ["regulatory_body"],
    }


@pytest.mark.parametrize(
    ("field_name", "error"),
    [
        ("content_class", "news_page_projection_item_content_class_required:news-1"),
        ("content_tags_json", "news_page_projection_item_content_tags_json_required:news-1"),
        ("content_classification_json", "news_page_projection_item_content_classification_json_required:news-1"),
    ],
)
def test_build_news_page_row_requires_item_content_projection_fields(field_name: str, error: str) -> None:
    item = _with_required_projection_context(
        {
            "news_item_id": "news-1",
            "title": "SEC delays tokenized stock decision",
            "summary": "The filing remains open.",
            "source_domain": "example.test",
            "canonical_url": "https://example.test/sec",
            "published_at_ms": 1000,
        }
    )
    item.pop(field_name)

    with pytest.raises(ValueError, match=error):
        _build_news_page_row(
            item=item,
            token_mentions=[],
            fact_candidates=[],
            story=_story_for_item(item),
            computed_at_ms=2000,
        )


def test_build_news_page_row_copies_item_level_agent_admission() -> None:
    row = build_news_page_row(
        item={
            "news_item_id": "news-1",
            "title": "Fed liquidity update lifts futures",
            "summary": "Macro desks repriced risk assets.",
            "source_domain": "example.test",
            "canonical_url": "https://example.test/fed-liquidity",
            "published_at_ms": 1000,
            "agent_admission_status": "eligible",
            "agent_admission_reason": "ready_market_driver",
            "agent_admission_json": {
                "status": "eligible",
                "reason": "ready_market_driver",
                "representative_news_item_id": "news-1",
                "version": "news_item_agent_admission_market_v2",
                "basis": {"market_scope": ["macro"]},
            },
            "agent_representative_news_item_id": "news-1",
        },
        token_mentions=[],
        fact_candidates=[],
        computed_at_ms=2000,
    )

    assert row["agent_admission_status"] == "eligible"
    assert row["agent_admission_reason"] == "ready_market_driver"
    assert row["agent_admission"] == {
        "status": "eligible",
        "reason": "ready_market_driver",
        "version": "news_item_agent_admission_market_v2",
        "basis": {"market_scope": ["macro"]},
        "representative_news_item_id": "news-1",
    }
    assert row["agent_representative_news_item_id"] == "news-1"


@pytest.mark.parametrize("source_quality_status", [None, "", 123])
def test_page_source_status_requires_explicit_source_quality_status(source_quality_status: object) -> None:
    with pytest.raises(ValueError, match="news_page_projection_item_source_quality_status_required:news-1"):
        build_news_page_row(
            item={
                "news_item_id": "news-1",
                "title": "Market update",
                "summary": "",
                "source_domain": "example.com",
                "published_at_ms": 1_000,
                "source_quality_status": source_quality_status,
                "provider_signal_json": {},
            },
            token_mentions=[],
            fact_candidates=[],
            computed_at_ms=2_000,
        )


def test_build_news_page_row_uses_stable_row_id() -> None:
    item = {
        "news_item_id": "news-1",
        "title": "Coinbase lists NEWX",
        "summary": "",
        "source_domain": "example.test",
        "canonical_url": "https://example.test/a",
        "published_at_ms": 1000,
    }

    first = build_news_page_row(
        item=item,
        token_mentions=[],
        fact_candidates=[],
        computed_at_ms=2000,
    )
    second = build_news_page_row(
        item=item,
        token_mentions=[],
        fact_candidates=[],
        computed_at_ms=3000,
    )

    assert first["row_id"] == second["row_id"]
    assert first["row_id"] != "news-1"


def test_story_row_id_uses_story_key() -> None:
    story = {
        "story_key": "news-story:subject:jpmorgan-citi-tokenized-deposit:t412000",
        "representative_news_item_id": "news-jpm",
        "member_news_item_ids": ["news-jpm", "news-citi"],
        "member_count": 2,
        "source_domains": ["bloomberg.com", "reuters.com"],
    }

    first = build_news_page_row(
        item={
            "news_item_id": "news-jpm",
            "story_key": story["story_key"],
            "title": "JPMorgan and Citi test tokenized deposits",
            "summary": "",
            "source_domain": "bloomberg.com",
            "canonical_url": "https://bloomberg.test/jpm-citi",
            "published_at_ms": 1000,
            "market_scope_json": {
                "scope": ["crypto"],
                "primary": "crypto",
                "status": "classified",
                "reason": "tokenized_deposit_subject",
                "basis": {"subject": "tokenized_deposit"},
                "version": "test_news_market_scope_v1",
            },
        },
        token_mentions=[],
        fact_candidates=[],
        story=story,
        computed_at_ms=2000,
    )
    second = build_news_page_row(
        item={
            "news_item_id": "news-citi",
            "story_key": story["story_key"],
            "title": "Citi joins JPMorgan tokenized deposit trial",
            "summary": "",
            "source_domain": "reuters.com",
            "canonical_url": "https://reuters.test/jpm-citi",
            "published_at_ms": 1001,
            "market_scope_json": {
                "scope": ["crypto"],
                "primary": "crypto",
                "status": "classified",
                "reason": "tokenized_deposit_subject",
                "basis": {"subject": "tokenized_deposit"},
                "version": "test_news_market_scope_v1",
            },
        },
        token_mentions=[],
        fact_candidates=[],
        story=story,
        computed_at_ms=3000,
    )
    fallback = build_news_page_row(
        item={
            "news_item_id": "news-jpm",
            "title": "JPMorgan and Citi test tokenized deposits",
            "summary": "",
            "source_domain": "bloomberg.com",
            "canonical_url": "https://bloomberg.test/jpm-citi",
            "published_at_ms": 1000,
        },
        token_mentions=[],
        fact_candidates=[],
        computed_at_ms=2000,
    )

    assert first["row_id"] == second["row_id"]
    assert first["row_id"] != fallback["row_id"]
    assert first["representative_news_item_id"] == "news-jpm"
    assert first["story_key"] == story["story_key"]


def test_build_news_page_row_marks_attention_for_unknown_token_without_facts() -> None:
    row = build_news_page_row(
        item={
            "news_item_id": "news-1",
            "title": "NEWX rallies",
            "summary": "",
            "source_domain": "example.test",
            "canonical_url": "https://example.test/a",
            "published_at_ms": 1000,
            "lifecycle_status": "processed",
        },
        token_mentions=[
            {
                "resolution_status": "unknown_attention",
                "display_symbol": "NEWX",
                "target_id": None,
            }
        ],
        fact_candidates=[],
        computed_at_ms=2000,
    )

    assert row["lifecycle_status"] == "attention"


def test_build_news_page_row_marks_accepted_when_no_attention_lanes() -> None:
    row = build_news_page_row(
        item={
            "news_item_id": "news-1",
            "title": "BTC ETF accepted",
            "summary": "",
            "source_domain": "example.test",
            "canonical_url": "https://example.test/a",
            "published_at_ms": 1000,
            "lifecycle_status": "processed",
        },
        token_mentions=[
            {
                "resolution_status": "known_symbol",
                "display_symbol": "BTC",
                "target_type": "cex_token",
                "target_id": "BTC",
            }
        ],
        fact_candidates=[{"event_type": "listing", "validation_status": "accepted"}],
        computed_at_ms=2000,
    )

    assert row["lifecycle_status"] == "accepted"
    assert row["token_lanes"][0]["lane"] == "resolved"


def test_build_news_page_row_includes_ready_compact_agent_brief() -> None:
    row = build_news_page_row(
        item={
            "news_item_id": "news-1",
            "title": "SOL ETF filing",
            "summary": "",
            "source_domain": "example.test",
            "canonical_url": "https://example.test/a",
            "published_at_ms": 1000,
            "agent_admission_status": "eligible",
            "agent_admission_reason": "eligible",
            "agent_representative_news_item_id": "news-1",
            "market_scope_json": {
                "scope": ["crypto"],
                "primary": "crypto",
                "status": "classified",
                "reason": "crypto_subject",
                "basis": {"subject": "sol_etf"},
                "version": "test_news_market_scope_v1",
            },
        },
        token_mentions=[],
        fact_candidates=[],
        agent_brief={
            "agent_run_id": "run-1",
            "status": "ready",
            "direction": "bullish",
            "decision_class": "driver",
            "brief_json": {
                "summary_zh": "SOL ETF 申请提升关注。",
                "market_read_zh": "叙事催化增强。",
                "event_type": "etf_filing",
                "market_domains": ["crypto"],
                "transmission_paths": [
                    {
                        "market_domain": "crypto",
                        "channel": "regulatory_attention",
                        "direction": "bullish",
                        "strength": "moderate",
                        "explanation_zh": "ETF 申请提升监管叙事。",
                    }
                ],
                "bull_view": {"strength": "strong", "thesis_zh": "新增需求预期"},
                "bear_view": {"strength": "weak", "thesis_zh": "审批仍不确定"},
                "affected_entities": [
                    {
                        "label": "SOL",
                        "symbol": "SOL",
                        "entity_type": "crypto_asset",
                        "market_domain": "crypto",
                        "target_id": "asset:sol",
                        "impact_direction": "bullish",
                        "reason_zh": "ETF 申请直接影响 SOL。",
                    }
                ],
                "data_gaps": [{"kind": "price_reaction"}],
            },
            "input_hash": "input-1",
            "artifact_version_hash": "artifact-1",
            "prompt_version": "prompt-v1",
            "schema_version": "schema-v1",
            "computed_at_ms": 3000,
        },
        computed_at_ms=4000,
    )

    assert row["agent_status"] == "ready"
    assert row["agent_brief_computed_at_ms"] == 3000
    assert row["agent_brief"] == {
        "status": "ready",
        "direction": "bullish",
        "decision_class": "driver",
        "summary_zh": "SOL ETF 申请提升关注。",
        "market_read_zh": "叙事催化增强。",
        "bull_strength": "strong",
        "bear_strength": "weak",
        "data_gap_count": 1,
        "computed_at_ms": 3000,
        "agent_admission_status": "eligible",
        "agent_admission_reason": "eligible",
        "representative_news_item_id": "news-1",
        "market_impacts": [],
        "bull_view": {"strength": "strong", "thesis_zh": "新增需求预期"},
        "bear_view": {"strength": "weak", "thesis_zh": "审批仍不确定"},
    }
    assert (
        not {
            "agent_run_id",
            "schema_version",
            "prompt_version",
            "validator_version",
            "artifact_version_hash",
            "input_hash",
        }
        & row["agent_brief"].keys()
    )


@pytest.mark.parametrize(
    ("market_impacts", "error"),
    [
        pytest.param("bad-impact", "news_page_projection_agent_brief_market_impacts_required:news-1", id="string"),
        pytest.param(
            {"label": "spot"}, "news_page_projection_agent_brief_market_impacts_required:news-1", id="mapping"
        ),
        pytest.param(["bad-impact"], "news_page_projection_agent_market_impact_required:news-1", id="non_mapping"),
        pytest.param([{}], "news_page_projection_agent_market_impact_label_required:news-1", id="missing_label"),
        pytest.param(
            [{"label": ""}], "news_page_projection_agent_market_impact_label_required:news-1", id="blank_label"
        ),
    ],
)
def test_build_news_page_row_rejects_malformed_agent_market_impacts(
    market_impacts: Any,
    error: str,
) -> None:
    with pytest.raises(ValueError, match=error):
        build_news_page_row(
            item=_base_projection_item(),
            token_mentions=[],
            fact_candidates=[],
            agent_brief={
                "status": "ready",
                "direction": "bullish",
                "decision_class": "driver",
                "brief_json": {
                    "summary_zh": "交易所上线带来流动性关注。",
                    "market_impacts": market_impacts,
                },
                "computed_at_ms": 2_000,
            },
            computed_at_ms=3_000,
        )


@pytest.mark.parametrize(
    ("brief_patch", "error"),
    [
        pytest.param({"bull_view": ["bad"]}, "news_page_projection_agent_brief_bull_view_required:news-1"),
        pytest.param({"bear_view": "bad"}, "news_page_projection_agent_brief_bear_view_required:news-1"),
        pytest.param({"data_gaps": {"kind": "missing"}}, "news_page_projection_agent_brief_data_gaps_required:news-1"),
    ],
)
def test_build_news_page_row_rejects_malformed_agent_brief_optional_sections(
    brief_patch: dict[str, Any],
    error: str,
) -> None:
    brief_json: dict[str, Any] = {"summary_zh": "交易所上线带来流动性关注。"}
    brief_json.update(brief_patch)

    with pytest.raises(ValueError, match=error):
        build_news_page_row(
            item=_base_projection_item(),
            token_mentions=[],
            fact_candidates=[],
            agent_brief={
                "status": "ready",
                "direction": "bullish",
                "decision_class": "driver",
                "brief_json": brief_json,
                "computed_at_ms": 2_000,
            },
            computed_at_ms=3_000,
        )


def test_build_news_page_row_projects_macro_event_flow_for_ready_market_scope() -> None:
    row = build_news_page_row(
        item={
            "news_item_id": "news-1",
            "title": "Fed liquidity update lifts futures",
            "summary": "Dollar and equities repriced after the update.",
            "source_domain": "example.test",
            "canonical_url": "https://example.test/fed-liquidity",
            "published_at_ms": 1_000,
            "agent_admission_status": "eligible",
            "agent_admission_reason": "ready_market_driver",
            "agent_representative_news_item_id": "news-1",
            "market_scope_json": {
                "scope": ["macro_policy", "equities", "fx"],
                "primary": "macro_policy",
                "status": "classified",
                "reason": "fed_liquidity_subject",
                "basis": {"subject": "fed_liquidity"},
                "version": "test_news_market_scope_v1",
            },
        },
        token_mentions=[
            {
                "resolution_status": "known_symbol",
                "display_symbol": "SPX",
                "target_type": "macro_asset",
                "target_id": "asset:spx",
            },
            {
                "resolution_status": "known_symbol",
                "display_symbol": "DXY",
                "target_type": "macro_asset",
                "target_id": "fx:dxy",
            },
        ],
        fact_candidates=[],
        agent_brief={
            "status": "ready",
            "direction": "bullish",
            "decision_class": "driver",
            "brief_json": {
                "summary_zh": "流动性信号推动风险资产重新定价。",
                "market_read_zh": "主线偏风险修复。",
            },
            "computed_at_ms": 2_000,
        },
        computed_at_ms=3_000,
    )

    assert row["macro_event_flow"] == {
        "window": "recent",
        "window_label": "近期",
        "severity": "high",
        "severity_label": "高",
        "category": "macro_policy",
        "category_label": "美联储",
        "impact": "mainline_driver",
        "impact_label": "改变主线",
        "watch": "SPX · DXY · 美联储",
    }


def test_page_signal_envelope_separates_provider_agent_display_and_alert() -> None:
    row = build_news_page_row(
        item={
            "news_item_id": "news-1",
            "title": "Binance lists EXAMPLE",
            "summary": "Listing starts today",
            "source_domain": "6551.io",
            "canonical_url": "https://example.com/news-1",
            "published_at_ms": 1_000,
            "agent_admission_status": "eligible",
            "agent_admission_reason": "ready_market_driver",
            "market_scope_json": {
                "scope": ["crypto"],
                "primary": "crypto",
                "status": "classified",
                "reason": "crypto_subject",
                "basis": {"subject": "exchange_listing"},
                "version": "test_news_market_scope_v1",
            },
            "provider_signal_json": {
                "source": "provider",
                "provider": "opennews",
                "status": "ready",
                "direction": "bullish",
                "score": 90,
                "method": "opennews.aiRating",
            },
        },
        token_mentions=[],
        fact_candidates=[],
        agent_brief={
            "status": "ready",
            "direction": "bullish",
            "decision_class": "watch",
            "brief_json": {"summary_zh": "交易所上线带来流动性关注。"},
            "computed_at_ms": 2_000,
        },
        computed_at_ms=3_000,
    )

    assert set(row["signal"]) == {"display_signal", "agent_signal", "alert_eligibility"}
    assert row["signal"]["display_signal"]["source"] == "agent"
    assert row["signal"]["agent_signal"]["status"] == "ready"
    assert row["signal"]["alert_eligibility"]["market_scope"]["primary"] == "crypto"
    assert row["signal"]["alert_eligibility"]["external_push_ready"] is True


def test_build_news_page_row_does_not_mix_provider_signal_into_ready_agent_brief() -> None:
    row = build_news_page_row(
        item={
            "news_item_id": "news-1",
            "title": "SOL ETF filing",
            "summary": "",
            "source_domain": "example.test",
            "canonical_url": "https://example.test/a",
            "published_at_ms": 1000,
            "agent_admission_status": "eligible",
            "agent_admission_reason": "ready_market_watch",
            "market_scope_json": {
                "scope": ["crypto"],
                "primary": "crypto",
                "status": "classified",
                "reason": "crypto_subject",
                "basis": {"subject": "sol_etf"},
                "version": "test_news_market_scope_v1",
            },
            "provider_signal_json": {
                "source": "provider",
                "provider": "opennews",
                "status": "ready",
                "direction": "bullish",
                "signal": "long",
                "score": 92,
                "grade": "A",
                "summary_en": "Provider summary",
                "method": "opennews.aiRating",
            },
        },
        token_mentions=[],
        fact_candidates=[],
        agent_brief={
            "agent_run_id": "run-1",
            "status": "ready",
            "direction": "bearish",
            "decision_class": "watch",
            "brief_json": {
                "summary_zh": "Agent sees event risk.",
                "market_read_zh": "风险仍待确认。",
                "bull_view": {"strength": "weak"},
                "bear_view": {"strength": "moderate"},
            },
            "computed_at_ms": 3000,
        },
        computed_at_ms=4000,
    )

    assert row["agent_status"] == "ready"
    assert row["signal"]["display_signal"]["source"] == "agent"
    assert row["signal"]["display_signal"]["direction"] == "bearish"
    assert "score" not in row["signal"]["display_signal"]
    assert "grade" not in row["signal"]["display_signal"]
    assert "provider_signal" not in row["signal"]
    assert row["provider_rating"] == {
        "provider": "opennews",
        "status": "ready",
        "direction": "bullish",
        "signal": "long",
        "score": 92,
        "grade": "A",
        "method": "opennews.aiRating",
    }
    assert row["signal"]["alert_eligibility"] == {
        "agent_status": "ready",
        "decision_class": "watch",
        "market_scope": {
            "scope": ["crypto"],
            "primary": "crypto",
            "status": "classified",
            "reason": "crypto_subject",
            "basis": {"subject": "sol_etf"},
            "version": "test_news_market_scope_v1",
        },
        "in_app_eligible": True,
        "external_push_ready": True,
        "external_push_basis": "agent_brief",
    }


@pytest.mark.parametrize("provider_signal_json", ["bullish", ["opennews"]])
def test_build_news_page_row_rejects_malformed_present_provider_signal(
    provider_signal_json: object,
) -> None:
    with pytest.raises(ValueError, match="news_page_projection_item_provider_signal_json_required:news-1"):
        build_news_page_row(
            item={
                "news_item_id": "news-1",
                "title": "SOL ETF filing",
                "summary": "",
                "source_domain": "example.test",
                "canonical_url": "https://example.test/a",
                "published_at_ms": 1000,
                "agent_admission_status": "eligible",
                "agent_admission_reason": "ready_market_watch",
                "provider_signal_json": provider_signal_json,
            },
            token_mentions=[],
            fact_candidates=[],
            computed_at_ms=4000,
        )


@pytest.mark.parametrize("score", [True, "90", 90.5])
def test_build_news_page_row_rejects_malformed_provider_rating_score_without_int_repair(
    score: object,
) -> None:
    with pytest.raises(ValueError, match="news_page_projection_provider_rating_score_required:news-1"):
        build_news_page_row(
            item={
                "news_item_id": "news-1",
                "title": "SOL ETF filing",
                "summary": "",
                "source_domain": "example.test",
                "canonical_url": "https://example.test/a",
                "published_at_ms": 1000,
                "agent_admission_status": "eligible",
                "agent_admission_reason": "ready_market_watch",
                "provider_signal_json": {
                    "provider": "opennews",
                    "status": "ready",
                    "direction": "bullish",
                    "score": score,
                    "method": "opennews.aiRating",
                },
            },
            token_mentions=[],
            fact_candidates=[],
            computed_at_ms=4000,
        )


def test_build_news_page_row_keeps_provider_candidate_separate_from_external_push_ready() -> None:
    row = build_news_page_row(
        item={
            "news_item_id": "news-1",
            "title": "High score provider alert",
            "summary": "",
            "source_domain": "example.test",
            "canonical_url": "https://example.test/a",
            "published_at_ms": 1000,
            "provider_signal_json": {
                "source": "provider",
                "provider": "opennews",
                "status": "ready",
                "direction": "bullish",
                "signal": "long",
                "score": 90,
                "grade": "A",
                "summary_zh": "Provider summary.",
                "method": "opennews.aiRating",
            },
        },
        token_mentions=[],
        fact_candidates=[],
        agent_brief={
            "agent_run_id": "run-1",
            "status": "insufficient",
            "direction": "neutral",
            "decision_class": "context",
            "brief_json": {
                "summary_zh": "证据不足，不能形成 agent brief。",
                "data_gaps": [{"kind": "missing_context"}],
            },
            "computed_at_ms": 3000,
        },
        computed_at_ms=4000,
    )

    eligibility = row["signal"]["alert_eligibility"]
    assert eligibility["in_app_eligible"] is False
    assert eligibility["external_push_ready"] is False
    assert eligibility["external_push_block_reason"] == "agent_brief_not_ready"
    assert "provider_signal" not in row["signal"]
    assert "provider_score" not in eligibility


def test_ready_market_watch_brief_sets_in_app_eligible_without_crypto_admission() -> None:
    row = build_news_page_row(
        item={
            "news_item_id": "news-spacex",
            "title": "SpaceX shares trade at higher valuation",
            "summary": "",
            "source_domain": "example.test",
            "canonical_url": "https://example.test/spacex",
            "published_at_ms": 1000,
            "agent_admission_status": "eligible",
            "agent_admission_reason": "market_wide_watch",
            "market_scope_json": {
                "scope": ["us_equity"],
                "primary": "us_equity",
                "status": "classified",
                "reason": "private_company_equity_context",
                "basis": {"subject": "private_company_equity_context"},
                "version": "test_news_market_scope_v1",
            },
            "provider_signal_json": {
                "source": "provider",
                "provider": "opennews",
                "status": "ready",
                "direction": "bullish",
                "score": 95,
                "grade": "A",
            },
            "provider_token_impacts_json": [{"symbol": "SPCX", "score": 95, "signal": "long"}],
        },
        token_mentions=[],
        fact_candidates=[],
        agent_brief={
            "agent_run_id": "run-spacex",
            "status": "ready",
            "direction": "bullish",
            "decision_class": "watch",
            "brief_json": {"summary_zh": "SpaceX valuation reset matters for private-market risk appetite."},
            "computed_at_ms": 1500,
        },
        computed_at_ms=2000,
    )

    assert "provider_signal" not in row["signal"]
    assert row["token_impacts"] == []
    assert row["market_scope"] == {
        "scope": ["us_equity"],
        "primary": "us_equity",
        "status": "classified",
        "reason": "private_company_equity_context",
        "basis": {"subject": "private_company_equity_context"},
        "version": "test_news_market_scope_v1",
    }
    assert row["signal"]["alert_eligibility"]["in_app_eligible"] is True
    assert row["signal"]["alert_eligibility"]["external_push_ready"] is True
    assert row["signal"]["alert_eligibility"]["market_scope"]["primary"] == "us_equity"
    assert "analysis_admission_status" not in row


def test_admitted_ready_brief_sets_external_push_ready() -> None:
    row = build_news_page_row(
        item={
            "news_item_id": "news-zec",
            "title": "Zcash discloses Orchard bug fix",
            "summary": "",
            "source_domain": "electriccoin.co",
            "canonical_url": "https://electriccoin.test/orchard",
            "published_at_ms": 1000,
            "agent_admission_status": "eligible",
            "agent_admission_reason": "ready_market_driver",
            "market_scope_json": {
                "scope": ["crypto"],
                "primary": "crypto",
                "status": "classified",
                "reason": "crypto_security_event",
                "basis": {"subject": "zcash_orchard"},
                "version": "test_news_market_scope_v1",
            },
            "provider_signal_json": {
                "source": "provider",
                "provider": "opennews",
                "status": "ready",
                "direction": "bearish",
                "score": 90,
            },
        },
        token_mentions=[],
        fact_candidates=[],
        agent_brief={
            "status": "ready",
            "direction": "bearish",
            "decision_class": "driver",
            "brief_json": {"summary_zh": "Zcash security event needs follow-up."},
            "computed_at_ms": 1500,
        },
        computed_at_ms=2000,
    )

    assert row["signal"]["alert_eligibility"]["in_app_eligible"] is True
    assert row["signal"]["alert_eligibility"]["external_push_ready"] is True


def test_ready_brief_without_summary_zh_does_not_use_market_read_for_external_push() -> None:
    row = build_news_page_row(
        item={
            "news_item_id": "news-zec",
            "title": "Zcash discloses Orchard bug fix",
            "summary": "",
            "source_domain": "electriccoin.co",
            "canonical_url": "https://electriccoin.test/orchard",
            "published_at_ms": 1000,
            "agent_admission_status": "eligible",
            "agent_admission_reason": "ready_market_driver",
            "market_scope_json": {
                "scope": ["crypto"],
                "primary": "crypto",
                "status": "classified",
                "reason": "crypto_security_event",
                "basis": {"subject": "zcash_orchard"},
                "version": "test_news_market_scope_v1",
            },
        },
        token_mentions=[],
        fact_candidates=[],
        agent_brief={
            "status": "ready",
            "direction": "bearish",
            "decision_class": "driver",
            "brief_json": {"market_read_zh": "Legacy market read cannot satisfy publishability."},
            "computed_at_ms": 1500,
        },
        computed_at_ms=2000,
    )

    eligibility = row["signal"]["alert_eligibility"]
    assert row["agent_brief"]["market_read_zh"] == "Legacy market read cannot satisfy publishability."
    assert "summary_zh" not in row["agent_brief"]
    assert eligibility["in_app_eligible"] is True
    assert eligibility["external_push_ready"] is False
    assert eligibility["external_push_block_reason"] == "agent_brief_missing_summary"


@pytest.mark.parametrize("field_name", ["direction", "decision_class"])
def test_page_signal_ready_agent_signal_requires_signal_fields_without_fallback(field_name: str) -> None:
    agent_signal = {
        "status": "ready",
        "direction": "bullish",
        "decision_class": "driver",
        "summary_zh": "Ready current signal.",
    }
    agent_signal.pop(field_name)

    with pytest.raises(ValueError, match=f"news_page_projection_agent_signal_{field_name}_required"):
        _page_signal(
            agent_signal=agent_signal,
            agent_admission_status="eligible",
            market_scope={"primary": "crypto"},
        )


def test_story_payload_includes_member_count_and_domains() -> None:
    story = {
        "story_key": "news-story:subject:spacex-valuation:t412000",
        "representative_news_item_id": "news-spacex-a",
        "member_news_item_ids": ["news-spacex-a", "news-spacex-b"],
        "member_count": 2,
        "source_domains": ["bloomberg.com", "wsj.com"],
        "provider_article_keys": ["opennews:100", "opennews:101"],
    }

    row = build_news_page_row(
        item={
            "news_item_id": "news-spacex-a",
            "story_key": story["story_key"],
            "title": "SpaceX tender offer values company higher",
            "summary": "",
            "source_domain": "bloomberg.com",
            "canonical_url": "https://bloomberg.test/spacex",
            "published_at_ms": 1000,
            "market_scope_json": {
                "scope": ["us_equity"],
                "primary": "us_equity",
                "status": "classified",
                "reason": "private_company_equity_context",
                "basis": {"subject": "spacex_valuation"},
                "version": "test_news_market_scope_v1",
            },
        },
        token_mentions=[],
        fact_candidates=[],
        story=story,
        computed_at_ms=2000,
    )

    assert row["story"] == story
    assert row["story"]["member_count"] == 2
    assert row["story"]["source_domains"] == ["bloomberg.com", "wsj.com"]


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("source_ids", "bloomberg-rss"),
        ("provider_article_keys", {"key": "opennews:100"}),
    ],
)
def test_story_payload_rejects_malformed_present_evidence_lists(field_name: str, value: Any) -> None:
    story = {
        "story_key": "news-story:subject:spacex-valuation:t412000",
        "representative_news_item_id": "news-spacex-a",
        "member_news_item_ids": ["news-spacex-a", "news-spacex-b"],
        "member_count": 2,
        "source_domains": ["bloomberg.com", "wsj.com"],
        field_name: value,
    }

    with pytest.raises(ValueError, match=f"news_page_projection_story_{field_name}_required:news-spacex-a"):
        build_news_page_row(
            item={
                "news_item_id": "news-spacex-a",
                "story_key": story["story_key"],
                "title": "SpaceX tender offer values company higher",
                "summary": "",
                "source_domain": "bloomberg.com",
                "canonical_url": "https://bloomberg.test/spacex",
                "published_at_ms": 1000,
            },
            token_mentions=[],
            fact_candidates=[],
            story=story,
            computed_at_ms=2000,
        )


def test_build_news_page_row_uses_pending_agent_brief_when_missing() -> None:
    row = build_news_page_row(
        item={
            "news_item_id": "news-1",
            "title": "SOL ETF filing",
            "summary": "",
            "source_domain": "example.test",
            "canonical_url": "https://example.test/a",
            "published_at_ms": 1000,
        },
        token_mentions=[],
        fact_candidates=[],
        computed_at_ms=4000,
    )

    assert row["agent_status"] == "pending"
    assert row["agent_brief_computed_at_ms"] is None
    assert row["agent_brief"] == {
        "status": "pending",
        "agent_admission_status": "eligible",
        "agent_admission_reason": "unit_test_market_driver",
        "representative_news_item_id": "news-1",
    }


@pytest.mark.parametrize(
    ("agent_brief", "error"),
    [
        ({}, "news_page_projection_agent_brief_status_required:news-1"),
        (
            {"status": "ready", "direction": "bullish", "decision_class": "driver"},
            "news_page_projection_agent_brief_json_required:news-1",
        ),
    ],
)
def test_build_news_page_row_rejects_malformed_current_agent_brief(agent_brief: dict[str, Any], error: str) -> None:
    with pytest.raises(ValueError, match=error):
        build_news_page_row(
            item={
                "news_item_id": "news-1",
                "title": "SOL ETF filing",
                "summary": "",
                "source_domain": "example.test",
                "canonical_url": "https://example.test/a",
                "published_at_ms": 1000,
            },
            token_mentions=[],
            fact_candidates=[],
            agent_brief=agent_brief,
            computed_at_ms=4000,
        )
