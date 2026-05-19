import pytest

from gmgn_twitter_intel.domains.news_intel.services.news_entity_extraction import NewsEntity
from gmgn_twitter_intel.domains.news_intel.services.news_token_mentions import build_news_token_mentions
from gmgn_twitter_intel.domains.token_intel.interfaces import TokenIdentityLookupResult


class FakeLookup:
    def __init__(self, *, address_status: str = "EXACT", symbol_status: str = "NIL") -> None:
        self.address_status = address_status
        self.symbol_status = symbol_status

    def resolve_address(self, *, chain_id: str | None, address: str):
        if self.address_status == "NIL":
            return TokenIdentityLookupResult(
                resolution_status="NIL",
                target_type=None,
                target_id=None,
                display_symbol=None,
                display_name=None,
                reason_codes=["ADDRESS_NOT_IN_REGISTRY"],
                candidate_targets=[],
            )
        return TokenIdentityLookupResult(
            resolution_status=self.address_status,
            target_type="Asset",
            target_id="asset:base:0x0",
            display_symbol="NEWX",
            display_name="NewX",
            reason_codes=["CHAIN_ADDRESS_EXACT"],
            candidate_targets=[],
        )

    def resolve_symbol(self, *, symbol: str):
        if self.symbol_status in {"UNKNOWN", "NIL"}:
            return TokenIdentityLookupResult(
                resolution_status=self.symbol_status,
                target_type=None,
                target_id=None,
                display_symbol=symbol,
                display_name=None,
                reason_codes=["SYMBOL_NOT_IN_REGISTRY"],
                candidate_targets=[],
            )
        target_type = "MarketInstrument" if self.symbol_status == "NON_CRYPTO" else "CexToken"
        target_id = "equity:AAPL" if self.symbol_status == "NON_CRYPTO" else f"cex:{symbol}"
        return TokenIdentityLookupResult(
            resolution_status=self.symbol_status,
            target_type=target_type,
            target_id=target_id,
            display_symbol=symbol,
            display_name=symbol.title(),
            reason_codes=[self.symbol_status],
            candidate_targets=[],
        )


def test_address_mentions_become_exact_address() -> None:
    mentions = build_news_token_mentions(
        news_item_id="news-1",
        entities=[
            NewsEntity(
                entity_id="e1",
                news_item_id="news-1",
                entity_type="ca",
                raw_value="0x0000000000000000000000000000000000000000",
                normalized_value="0x0000000000000000000000000000000000000000",
                chain="base",
                span_start=0,
                span_end=42,
                text_surface="summary",
                confidence=1.0,
                extraction_policy_version="v",
                created_at_ms=1,
            )
        ],
        identity_lookup=FakeLookup(),
        now_ms=1,
    )
    assert mentions[0].resolution_status == "exact_address"
    assert mentions[0].target_id == "asset:base:0x0"


@pytest.mark.parametrize(
    ("identity_status", "expected_status"),
    [
        ("EXACT", "known_symbol"),
        ("UNIQUE_BY_CONTEXT", "unique_by_context"),
        ("AMBIGUOUS", "ambiguous_symbol"),
        ("UNKNOWN", "unknown_attention"),
        ("NIL", "unknown_attention"),
        ("NON_CRYPTO", "non_crypto"),
    ],
)
def test_symbol_identity_statuses_map_to_v1_lowercase_statuses(
    identity_status: str,
    expected_status: str,
) -> None:
    mentions = build_news_token_mentions(
        news_item_id="news-1",
        entities=[_symbol_entity("e1", "$NEWX", "NEWX")],
        identity_lookup=FakeLookup(symbol_status=identity_status),
        now_ms=1,
    )

    assert mentions[0].resolution_status == expected_status


def test_unknown_symbol_goes_to_attention_lane() -> None:
    mentions = build_news_token_mentions(
        news_item_id="news-1",
        entities=[_symbol_entity("e1", "$NEWX", "NEWX")],
        identity_lookup=FakeLookup(symbol_status="NIL"),
        now_ms=1,
    )
    assert mentions[0].resolution_status == "unknown_attention"
    assert mentions[0].target_id is None


def _symbol_entity(entity_id: str, raw_value: str, normalized_value: str) -> NewsEntity:
    return NewsEntity(
        entity_id=entity_id,
        news_item_id="news-1",
        entity_type="symbol",
        raw_value=raw_value,
        normalized_value=normalized_value,
        chain=None,
        span_start=0,
        span_end=len(raw_value),
        text_surface="title",
        confidence=0.8,
        extraction_policy_version="v",
        created_at_ms=1,
    )
