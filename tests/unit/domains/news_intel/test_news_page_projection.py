from __future__ import annotations

from parallax.domains.news_intel._constants import NEWS_PAGE_PROJECTION_VERSION
from parallax.domains.news_intel.services.news_page_projection import build_news_page_row


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
    assert row["story_key"] == ""
    assert row["story"] == {}
    assert row["market_scope"] == {}
    assert "analysis_admission_status" not in row
    assert "analysis_admission_reason" not in row
    assert "analysis_admission" not in row
    assert "story_id" not in row
    assert row["source"] == {
        "source_id": "example-rss",
        "source_domain": "example.test",
        "coverage_tags": [],
        "source_quality_status": "unknown",
    }
    assert row["projection_version"] == NEWS_PAGE_PROJECTION_VERSION


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


def test_page_source_status_defaults_unknown_when_source_quality_missing() -> None:
    row = build_news_page_row(
        item={
            "news_item_id": "news-1",
            "title": "Market update",
            "summary": "",
            "source_domain": "example.com",
            "published_at_ms": 1_000,
            "source_quality_status": None,
            "provider_signal_json": {},
        },
        token_mentions=[],
        fact_candidates=[],
        computed_at_ms=2_000,
    )

    assert row["source"]["source_quality_status"] == "unknown"


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
                "bull_view": {"strength": "strong", "thesis_zh": "新增需求预期"},
                "bear_view": {"strength": "weak", "thesis_zh": "审批仍不确定"},
                "market_impacts": [
                    {
                        "label": "SOL",
                        "market_type": "crypto",
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
        "agent_run_id": "run-1",
        "schema_version": "schema-v1",
        "prompt_version": "prompt-v1",
        "artifact_version_hash": "artifact-1",
        "input_hash": "input-1",
        "agent_admission_status": "needs_review",
        "agent_admission_reason": "",
        "representative_news_item_id": "news-1",
        "bull_view": {"strength": "strong", "thesis_zh": "新增需求预期"},
        "bear_view": {"strength": "weak", "thesis_zh": "审批仍不确定"},
        "market_impacts": [
            {
                "label": "SOL",
                "market_type": "crypto",
                "target_id": "asset:sol",
                "impact_direction": "bullish",
                "reason_zh": "ETF 申请直接影响 SOL。",
            }
        ],
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

    assert set(row["signal"]) == {"display_signal", "provider_signal", "agent_signal", "alert_eligibility"}
    assert row["signal"]["display_signal"]["source"] == "agent"
    assert row["signal"]["provider_signal"]["provider"] == "opennews"
    assert row["signal"]["agent_signal"]["status"] == "ready"
    assert row["signal"]["alert_eligibility"]["market_scope"]["primary"] == "crypto"
    assert row["signal"]["alert_eligibility"]["external_push_ready"] is True


def test_build_news_page_row_preserves_provider_signal_without_masking_ready_agent_brief() -> None:
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
    assert row["signal"]["display_signal"]["score"] == 92
    assert row["signal"]["provider_signal"] == {
        "source": "provider",
        "provider": "opennews",
        "status": "ready",
        "direction": "bullish",
        "label_zh": "利好",
        "signal": "long",
        "score": 92,
        "grade": "A",
        "summary_en": "Provider summary",
        "method": "opennews.aiRating",
    }
    assert row["signal"]["alert_eligibility"] == {
        "agent_status": "ready",
        "decision_class": "watch",
        "provider_status": "ready",
        "provider_score": 92,
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
                "basis": {"provider_score_is_evidence_only": True},
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

    assert row["signal"]["provider_signal"]["score"] == 95
    assert row["market_scope"] == {
        "scope": ["us_equity"],
        "primary": "us_equity",
        "status": "classified",
        "reason": "private_company_equity_context",
        "basis": {"provider_score_is_evidence_only": True},
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
        "agent_admission_status": "needs_review",
        "agent_admission_reason": "",
        "representative_news_item_id": "news-1",
    }
