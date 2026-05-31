from parallax.domains.news_intel.services.news_fact_candidates import build_fact_candidates
from parallax.domains.news_intel.services.news_token_mentions import NewsTokenMention


def test_official_listing_candidate_can_be_accepted() -> None:
    candidates = build_fact_candidates(
        news_item_id="news-1",
        source_role="official_exchange",
        source_domain="coinbase.com",
        authority_scope={"event_types": ["exchange_listing"], "domains": ["coinbase.com"]},
        title="Coinbase lists BTC for trading",
        summary="Trading starts today",
        body_text="",
        token_mentions=[_mention("known_symbol")],
        now_ms=1,
    )
    assert candidates[0].event_type == "exchange_listing"
    assert candidates[0].validation_status == "accepted"


def test_specialist_media_listing_stays_attention_until_corroborated() -> None:
    candidates = build_fact_candidates(
        news_item_id="news-1",
        source_role="specialist_media",
        source_domain="example.com",
        authority_scope={},
        title="Coinbase lists BTC for trading",
        summary="Trading starts today",
        body_text="",
        token_mentions=[_mention("known_symbol")],
        now_ms=1,
    )
    assert candidates[0].validation_status == "attention"
    assert "source_not_authoritative_for_event_type" in candidates[0].rejection_reasons


def test_official_exchange_listing_outside_authority_scope_stays_attention() -> None:
    candidates = build_fact_candidates(
        news_item_id="news-1",
        source_role="official_exchange",
        source_domain="coinbase.com",
        authority_scope={"event_types": ["exchange_delisting"], "domains": ["coinbase.com"]},
        title="Coinbase lists BTC for trading",
        summary="Trading starts today",
        body_text="",
        token_mentions=[_mention("known_symbol")],
        now_ms=1,
    )
    assert candidates[0].validation_status == "attention"
    assert "event_type_out_of_authority_scope" in candidates[0].rejection_reasons


def test_official_exchange_listing_without_authority_scope_stays_attention() -> None:
    candidates = build_fact_candidates(
        news_item_id="news-1",
        source_role="official_exchange",
        source_domain="coinbase.com",
        authority_scope={},
        title="Coinbase lists BTC for trading",
        summary="Trading starts today",
        body_text="",
        token_mentions=[_mention("known_symbol")],
        now_ms=1,
    )
    assert candidates[0].validation_status == "attention"
    assert "authority_scope_missing" in candidates[0].rejection_reasons


def test_official_issuer_etf_approval_prefers_etf_fund_flow_over_regulatory_attention() -> None:
    candidates = build_fact_candidates(
        news_item_id="news-1",
        source_role="official_issuer",
        source_domain="issuer.example",
        authority_scope={"event_types": ["etf_fund_flow"], "domains": ["issuer.example"]},
        title="Issuer ETF approved with BTC inflow",
        summary="Spot ETF approved and reports net flow.",
        body_text="",
        token_mentions=[_mention("known_symbol")],
        now_ms=1,
    )

    assert candidates[0].event_type == "etf_fund_flow"
    assert candidates[0].validation_status == "accepted"
    assert all(
        candidate.event_type != "regulatory_action" or candidate.validation_status != "attention"
        for candidate in candidates
    )


def test_official_regulator_etf_approval_emits_accepted_regulatory_action() -> None:
    candidates = build_fact_candidates(
        news_item_id="news-1",
        source_role="official_regulator",
        source_domain="sec.gov",
        authority_scope={"event_types": ["regulatory_action"], "domains": ["sec.gov"]},
        title="SEC approved spot Bitcoin ETF",
        summary="The regulator approved the spot Bitcoin ETF.",
        body_text="",
        token_mentions=[_mention("known_symbol")],
        now_ms=1,
    )

    accepted = [candidate for candidate in candidates if candidate.validation_status == "accepted"]
    assert [(candidate.event_type, candidate.validation_status) for candidate in accepted] == [
        ("regulatory_action", "accepted")
    ]
    assert all(
        candidate.event_type != "etf_fund_flow" or candidate.validation_status != "attention"
        for candidate in candidates
    )


def test_unknown_symbol_candidate_goes_attention_not_accepted() -> None:
    candidates = build_fact_candidates(
        news_item_id="news-1",
        source_role="specialist_media",
        source_domain="example.com",
        authority_scope={},
        title="Coinbase lists NEWX for trading",
        summary="Trading starts today",
        body_text="",
        token_mentions=[_mention("unknown_attention")],
        now_ms=1,
    )
    assert candidates[0].validation_status == "attention"
    assert "target_identity_not_production_eligible" in candidates[0].rejection_reasons


def test_non_crypto_target_is_not_production_eligible_for_accepted_fact() -> None:
    candidates = build_fact_candidates(
        news_item_id="news-1",
        source_role="official_exchange",
        source_domain="coinbase.com",
        authority_scope={"event_types": ["exchange_listing"], "domains": ["coinbase.com"]},
        title="Coinbase lists AAPL for trading",
        summary="Trading starts today",
        body_text="",
        token_mentions=[_mention("non_crypto")],
        now_ms=1,
    )
    assert candidates[0].validation_status == "attention"
    assert "target_identity_not_production_eligible" in candidates[0].rejection_reasons


def _mention(status: str = "known_symbol") -> NewsTokenMention:
    production = status in {"exact_address", "known_symbol", "unique_by_context"}
    non_crypto = status == "non_crypto"
    return NewsTokenMention(
        mention_id="m1",
        news_item_id="news-1",
        entity_id="e1",
        observed_symbol="BTC",
        chain_id=None,
        address=None,
        resolution_status=status,
        target_type="MarketInstrument" if non_crypto else "CexToken" if production else None,
        target_id="equity:AAPL" if non_crypto else "cex:BTC" if production else None,
        display_symbol="BTC",
        display_name="Bitcoin",
        reason_codes=[],
        candidate_targets=[],
        evidence_strength="medium",
        confidence=0.8,
        created_at_ms=1,
    )
