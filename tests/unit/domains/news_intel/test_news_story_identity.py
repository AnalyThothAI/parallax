from __future__ import annotations

from parallax.domains.news_intel.services.news_story_identity import build_news_story_identity


def _item(
    *,
    news_item_id: str,
    title: str,
    published_at_ms: int,
    provider_article_keys_json: list[str] | None = None,
    provider_canonical_url: str = "",
    summary: str = "",
) -> dict[str, object]:
    payload: dict[str, object] = {
        "news_item_id": news_item_id,
        "title": title,
        "summary": summary,
        "published_at_ms": published_at_ms,
    }
    if provider_article_keys_json is not None:
        payload["provider_type"] = "opennews"
        payload["provider_article_keys_json"] = provider_article_keys_json
    if provider_canonical_url:
        payload["provider_canonical_url"] = provider_canonical_url
    return payload


def _identity(
    item: dict[str, object],
    *,
    token_mentions: list[dict[str, object]] | None = None,
    fact_candidates: list[dict[str, object]] | None = None,
    market_scope: dict[str, object] | None = None,
):
    return build_news_story_identity(
        item=item,
        token_mentions=token_mentions or [],
        fact_candidates=fact_candidates or [],
        market_scope=market_scope or {"scope": ["crypto"], "primary": "crypto"},
    )


def test_spacex_variants_group_to_same_story_key() -> None:
    first = _identity(
        _item(
            news_item_id="spacex-1",
            title="WSJ: SpaceX weighs tender offer at $350 billion valuation",
            published_at_ms=1_735_689_600_000,
        )
    )
    second = _identity(
        _item(
            news_item_id="spacex-2",
            title="NEW: SpaceX said to consider share sale valuing company around $350B",
            published_at_ms=1_735_692_000_000,
        )
    )

    assert first.story_key == second.story_key
    assert first.confidence == "strong"


def test_different_spacex_stories_within_time_bucket_do_not_merge() -> None:
    valuation = _identity(
        _item(
            news_item_id="spacex-valuation",
            title="SpaceX weighs tender offer at $350 billion valuation",
            published_at_ms=1_735_689_600_000,
        )
    )
    launch = _identity(
        _item(
            news_item_id="spacex-launch",
            title="SpaceX launches Starship test flight from Texas",
            published_at_ms=1_735_692_000_000,
        )
    )

    assert valuation.story_key != launch.story_key


def test_jpm_citi_tokenized_deposit_variants_group_to_same_story_key() -> None:
    first = _identity(
        _item(
            news_item_id="deposit-1",
            title="JPMorgan and Citi test tokenized deposit payments on a shared ledger",
            published_at_ms=1_735_689_600_000,
        )
    )
    second = _identity(
        _item(
            news_item_id="deposit-2",
            title="* Citi, JPM expand tokenized deposits pilot for bank clients",
            published_at_ms=1_735_693_200_000,
        )
    )

    assert first.story_key == second.story_key
    assert first.confidence == "strong"


def test_zcash_orchard_follow_ups_group_to_same_story_key() -> None:
    first = _identity(
        _item(
            news_item_id="zcash-1",
            title="Zcash Orchard upgrade reduces shielded transaction friction",
            published_at_ms=1_735_689_600_000,
        )
    )
    second = _identity(
        _item(
            news_item_id="zcash-2",
            title="- Follow-up: Orchard wallet changes lift Zcash privacy usage",
            published_at_ms=1_735_695_600_000,
        )
    )

    assert first.story_key == second.story_key
    assert first.confidence == "strong"


def test_trump_iran_fragments_group_when_subject_time_are_close() -> None:
    first = _identity(
        _item(
            news_item_id="iran-1",
            title="Trump warns Iran over nuclear talks",
            published_at_ms=1_735_689_600_000,
        ),
        market_scope={"scope": ["macro_rates", "broad_risk"], "primary": "macro_rates"},
    )
    second = _identity(
        _item(
            news_item_id="iran-2",
            title="Iran says Trump comments complicate negotiations",
            published_at_ms=1_735_693_200_000,
        ),
        market_scope={"scope": ["macro_rates", "broad_risk"], "primary": "macro_rates"},
    )

    assert first.story_key == second.story_key
    assert first.confidence == "strong"


def test_different_trump_iran_events_within_close_time_do_not_merge() -> None:
    talks = _identity(
        _item(
            news_item_id="iran-talks",
            title="Trump warns Iran over nuclear talks",
            published_at_ms=1_735_689_600_000,
        )
    )
    sanctions = _identity(
        _item(
            news_item_id="iran-sanctions",
            title="Trump administration expands Iran oil sanctions",
            published_at_ms=1_735_690_200_000,
        )
    )

    assert talks.story_key != sanctions.story_key


def test_trump_iran_nuclear_sanctions_do_not_merge_with_nuclear_talks() -> None:
    talks = _identity(
        _item(
            news_item_id="iran-nuclear-talks",
            title="Trump warns Iran over nuclear talks",
            published_at_ms=1_735_689_600_000,
        )
    )
    sanctions = _identity(
        _item(
            news_item_id="iran-nuclear-sanctions",
            title="Trump administration expands Iran nuclear sanctions",
            published_at_ms=1_735_690_200_000,
        )
    )

    assert talks.story_key != sanctions.story_key


def test_weak_unrelated_titles_do_not_over_merge() -> None:
    first = _identity(
        _item(
            news_item_id="weak-1",
            title="Markets move as investors weigh latest headlines",
            published_at_ms=1_735_689_600_000,
        )
    )
    second = _identity(
        _item(
            news_item_id="weak-2",
            title="Analysts see mixed trading after overnight update",
            published_at_ms=1_735_690_200_000,
        )
    )

    assert first.story_key != second.story_key
    assert first.confidence == "weak"
    assert second.confidence == "weak"


def test_source_prefixes_and_bullet_prefixes_do_not_affect_key() -> None:
    prefixed = _identity(
        _item(
            news_item_id="prefix-1",
            title="WSJ: * Ukraine and Russia sanctions talks advance in Europe",
            published_at_ms=1_735_689_600_000,
        )
    )
    plain = _identity(
        _item(
            news_item_id="prefix-2",
            title="Ukraine Russia sanctions talks advance in Europe",
            published_at_ms=1_735_690_200_000,
        )
    )

    assert prefixed.story_key == plain.story_key


def test_opennews_article_key_does_not_become_story_identity() -> None:
    identity = _identity(
        _item(
            news_item_id="article-1",
            title="SpaceX valuation story",
            published_at_ms=1_735_689_600_000,
            provider_article_keys_json=["opennews:2367422"],
        )
    )

    assert identity.story_key != "news-story:opennews-article:2367422"
    assert identity.basis["method"] != "opennews_article_key"


def test_opennews_same_title_items_still_group_without_article_identity() -> None:
    first = _identity(
        _item(
            news_item_id="article-1",
            title="SpaceX valuation story",
            published_at_ms=1_735_689_600_000,
            provider_article_keys_json=["opennews:2367422"],
        )
    )
    second = _identity(
        _item(
            news_item_id="article-2",
            title="SpaceX valuation story",
            published_at_ms=1_735_689_660_000,
            provider_article_keys_json=["2367422"],
        )
    )

    assert first.story_key == second.story_key
    assert first.basis["market_scope"] == ["crypto"]
    assert first.basis["market_scope_primary"] == "crypto"
    assert "admission_status" not in first.basis


def test_exchange_listing_variants_group_to_same_event_story_key() -> None:
    first = _identity(
        _item(
            news_item_id="upbit-citrea-1",
            title="[Trade] Market Support for Citrea(CTR) (BTC, USDT Market)",
            published_at_ms=1_780_972_202_947,
            provider_article_keys_json=["opennews:2599805"],
            provider_canonical_url="https://upbit.com/service_center/notice?id=6282",
        )
    )
    second = _identity(
        _item(
            news_item_id="upbit-citrea-2",
            title="UPBIT LISTING:【交易】Citrea(CTR)（BTC、USDT市场）市场支撑",
            published_at_ms=1_780_972_203_025,
            provider_article_keys_json=["opennews:2599811"],
        )
    )
    third = _identity(
        _item(
            news_item_id="upbit-citrea-3",
            title="UPBIT: UPBIT LISTING:【交易】Citrea(CTR)（BTC、USDT市场）市场支撑",
            published_at_ms=1_780_972_203_025,
            provider_article_keys_json=["opennews:2599812"],
        )
    )

    assert first.story_key == second.story_key == third.story_key
    assert first.story_key.startswith("news-story:event:exchange-listing:upbit:ctr:btc-usdt:t")
    assert first.confidence == "strong"
    assert first.basis["method"] == "exchange_listing_event_key"


def test_exchange_listing_keeps_different_venues_separate() -> None:
    upbit = _identity(
        _item(
            news_item_id="upbit-citrea",
            title="[Trade] Market Support for Citrea(CTR) (BTC, USDT Market)",
            published_at_ms=1_780_972_202_947,
        )
    )
    bithumb = _identity(
        _item(
            news_item_id="bithumb-citrea",
            title="Bithumb Listing: [마켓 추가] 시트레아(CTR) 원화 마켓 추가",
            published_at_ms=1_780_969_207_417,
        )
    )

    assert upbit.story_key != bithumb.story_key


def test_exchange_listing_detects_provider_url_and_multilingual_action() -> None:
    identity = _identity(
        _item(
            news_item_id="upbit-citrea-official",
            title="【交易】Citrea(CTR)（BTC、USDT市场）市场支撑",
            published_at_ms=1_780_972_203_025,
            provider_canonical_url="https://upbit.com/service_center/notice?id=6282",
        )
    )

    assert identity.story_key.startswith("news-story:event:exchange-listing:upbit:ctr:btc-usdt:t")
    assert identity.basis["method"] == "exchange_listing_event_key"


def test_exchange_listing_detects_krw_quote_aliases() -> None:
    identity = _identity(
        _item(
            news_item_id="bithumb-citrea-krw",
            title="Bithumb Listing: [마켓 추가] 시트레아(CTR) 원화 마켓 추가",
            published_at_ms=1_780_969_207_417,
        )
    )

    assert identity.story_key.startswith("news-story:event:exchange-listing:bithumb:ctr:krw:t")


def test_article_key_alone_is_ignored() -> None:
    legacy_item = {
        "news_item_id": "legacy-article",
        "title": "Different title for a legacy article key",
        "published_at_ms": 1_735_689_600_000,
        "article_key": "opennews:2367422",
    }

    identity = _identity(legacy_item)

    assert identity.story_key != "news-story:opennews-article:2367422"


def test_provider_article_keys_never_drive_story_identity() -> None:
    item = {
        "news_item_id": "wrong-provider",
        "title": "Different title for a non-opennews article key",
        "published_at_ms": 1_735_689_600_000,
        "provider_type": "rss",
        "provider_article_keys_json": ["opennews:2367422"],
    }

    identity = _identity(item)

    assert identity.story_key != "news-story:opennews-article:2367422"


def test_strong_story_variants_crossing_12h_floor_bucket_boundary_group() -> None:
    boundary_ms = 1_735_689_600_000
    before = _identity(
        _item(
            news_item_id="spacex-before-boundary",
            title="SpaceX weighs tender offer at $350 billion valuation",
            published_at_ms=boundary_ms - 60_000,
        )
    )
    after = _identity(
        _item(
            news_item_id="spacex-after-boundary",
            title="SpaceX said to consider share sale valuing company around $350B",
            published_at_ms=boundary_ms + 60_000,
        )
    )

    assert before.story_key == after.story_key


def test_material_story_variants_crossing_6h_floor_bucket_boundary_group() -> None:
    boundary_ms = 1_735_689_600_000
    before = _identity(
        _item(
            news_item_id="material-before-boundary",
            title="WSJ: ETF issuer files revised Solana fund prospectus with SEC",
            published_at_ms=boundary_ms - 60_000,
        )
    )
    after = _identity(
        _item(
            news_item_id="material-after-boundary",
            title="ETF issuer files revised Solana fund prospectus with SEC",
            published_at_ms=boundary_ms + 60_000,
        )
    )

    assert before.story_key == after.story_key


def test_story_identity_basis_carries_market_scope_for_subject_keys() -> None:
    identity = _identity(
        _item(
            news_item_id="spacex-scope",
            title="SpaceX weighs tender offer at $350 billion valuation",
            published_at_ms=1_735_689_600_000,
        ),
        market_scope={"scope": ["private_company"], "primary": "private_company"},
    )

    assert identity.basis["market_scope"] == ["private_company"]
    assert identity.basis["market_scope_primary"] == "private_company"
    assert "admission_status" not in identity.basis


def test_build_news_story_identity_requires_keyword_arguments() -> None:
    item = _item(
        news_item_id="api-1",
        title="Markets move as investors weigh latest headlines",
        published_at_ms=1_735_689_600_000,
    )

    try:
        build_news_story_identity(item, [], [], {"scope": ["crypto"], "primary": "crypto"})  # type: ignore[misc]
    except TypeError:
        return

    raise AssertionError("build_news_story_identity accepted positional arguments")
