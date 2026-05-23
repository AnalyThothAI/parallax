from gmgn_twitter_intel.domains.news_intel.services.source_authority import validate_source_authority


def test_official_exchange_accepts_in_scope_listing() -> None:
    decision = validate_source_authority(
        source_role="official_exchange",
        authority_scope={"event_types": ["exchange_listing"], "domains": ["coinbase.com"]},
        event_type="exchange_listing",
        source_domain="coinbase.com",
        affected_targets=[{"production_eligible": True}],
        realis="actual",
    )

    assert decision.acceptance_allowed is True
    assert decision.rejection_reasons == []


def test_official_protocol_rejects_out_of_scope_exchange_listing() -> None:
    decision = validate_source_authority(
        source_role="official_protocol",
        authority_scope={"event_types": ["protocol_upgrade"], "domains": ["ethereum.org"]},
        event_type="exchange_listing",
        source_domain="ethereum.org",
        affected_targets=[{"production_eligible": True}],
        realis="actual",
    )

    assert decision.acceptance_allowed is False
    assert "source_not_authoritative_for_event_type" in decision.rejection_reasons


def test_authority_scope_rejects_event_outside_configured_scope() -> None:
    decision = validate_source_authority(
        source_role="official_exchange",
        authority_scope={"event_types": ["exchange_delisting"], "domains": ["coinbase.com"]},
        event_type="exchange_listing",
        source_domain="coinbase.com",
        affected_targets=[{"production_eligible": True}],
        realis="actual",
    )

    assert decision.acceptance_allowed is False
    assert "event_type_out_of_authority_scope" in decision.rejection_reasons


def test_official_exchange_rejects_missing_authority_scope() -> None:
    decision = validate_source_authority(
        source_role="official_exchange",
        authority_scope={},
        event_type="exchange_listing",
        source_domain="coinbase.com",
        affected_targets=[{"production_eligible": True}],
        realis="actual",
    )

    assert decision.acceptance_allowed is False
    assert "authority_scope_missing" in decision.rejection_reasons


def test_authority_scope_accepts_in_scope_target_dict() -> None:
    decision = validate_source_authority(
        source_role="official_exchange",
        authority_scope={
            "event_types": ["exchange_listing"],
            "domains": ["coinbase.com"],
            "targets": [{"target_type": "CexToken", "target_id": "cex:BTC"}],
        },
        event_type="exchange_listing",
        source_domain="coinbase.com",
        affected_targets=[{"production_eligible": True, "target_type": "CexToken", "target_id": "cex:BTC"}],
        realis="actual",
    )

    assert decision.acceptance_allowed is True
    assert decision.rejection_reasons == []


def test_authority_scope_rejects_out_of_scope_target_dict() -> None:
    decision = validate_source_authority(
        source_role="official_exchange",
        authority_scope={
            "event_types": ["exchange_listing"],
            "domains": ["coinbase.com"],
            "targets": [{"target_type": "CexToken", "target_id": "cex:ETH"}],
        },
        event_type="exchange_listing",
        source_domain="coinbase.com",
        affected_targets=[{"production_eligible": True, "target_type": "CexToken", "target_id": "cex:BTC"}],
        realis="actual",
    )

    assert decision.acceptance_allowed is False
    assert "target_out_of_authority_scope" in decision.rejection_reasons
