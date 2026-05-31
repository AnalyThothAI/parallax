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
