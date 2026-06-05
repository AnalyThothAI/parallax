from parallax.domains.news_intel.services.news_entity_extraction import extract_news_entities


def test_extract_news_entities_reuses_span_aware_address_and_symbol_extraction() -> None:
    entities = extract_news_entities(
        news_item_id="news-1",
        title="New token $NEWX launches on Base",
        summary="CA 0x0000000000000000000000000000000000000000 on Base",
        body_text="",
        now_ms=1,
    )

    types = {entity.entity_type for entity in entities}
    assert "symbol" in types
    assert "ca" in types
    assert all(entity.news_item_id == "news-1" for entity in entities)
    assert {entity.text_surface for entity in entities} >= {"title", "summary"}


def test_extract_news_entities_dedupes_duplicate_title_body_by_repository_identity() -> None:
    text = (
        "ZEC plunged 50% following the counterfeiting vulnerability, but some whales are still "
        "bravely buying the dip. A newly created wallet withdrew 37,316 $ZEC($13.12M) "
        "from #Binance 40 minutes ago."
    )

    entities = extract_news_entities(
        news_item_id="news-zec",
        title=text,
        summary="",
        body_text=text,
        now_ms=1,
    )

    repository_identities = [
        (
            entity.news_item_id,
            entity.entity_type,
            entity.normalized_value,
            entity.chain or "",
            entity.span_start,
            entity.span_end,
        )
        for entity in entities
    ]
    assert len(repository_identities) == len(set(repository_identities))
    assert [(entity.entity_type, entity.normalized_value, entity.text_surface) for entity in entities] == [
        ("symbol", "ZEC", "title"),
        ("hashtag", "binance", "title"),
    ]
