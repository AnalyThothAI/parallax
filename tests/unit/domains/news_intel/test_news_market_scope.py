from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from parallax.domains.news_intel._constants import NEWS_MARKET_SCOPE_VERSION
from parallax.domains.news_intel.services.news_market_scope import (
    NewsMarketScope,
    classify_news_market_scope,
)

_OLD_ADMISSION_REASONS = {
    "non_crypto_subject",
    "no_crypto_native_evidence",
    "provider_evidence_only",
    "analysis_not_admitted",
}


def test_private_company_and_us_equity_are_market_scope_metadata() -> None:
    private_company = _classify(
        item=_item(
            title="SpaceX share sale values private company above $350 billion",
            summary="The tender offer would lift the private space company's valuation.",
            content_class="low_signal",
        )
    )
    us_equity = _classify(
        item=_item(
            title="Nvidia shares climb as AI server demand boosts chip outlook",
            summary="The US equity gained after analysts raised semiconductor estimates.",
            content_class="ai_semiconductors",
        ),
        token_mentions=[
            _mention(
                "NVDA",
                target_type="MarketInstrument",
                target_id="equity:NVDA",
                resolution_status="non_crypto",
                market_type="equity",
            )
        ],
    )

    assert private_company.primary == "private_company"
    assert private_company.status == "classified"
    assert private_company.to_payload()["scope"] == ["private_company"]
    assert private_company.reason not in _OLD_ADMISSION_REASONS

    assert us_equity.primary == "us_equity"
    assert "us_equity" in us_equity.scope
    assert "ai_semiconductors" in us_equity.scope
    assert us_equity.reason not in _OLD_ADMISSION_REASONS


def test_macro_rates_without_crypto_is_classified_as_macro_rates() -> None:
    market_scope = _classify(
        item=_item(
            title="Fed officials push back on rate cut bets as Treasury yields rise",
            summary="Macro traders reassess the path for liquidity and broad risk assets.",
            content_class="rates_fed",
        )
    )

    assert market_scope.primary == "macro_rates"
    assert market_scope.scope == ("macro_rates", "broad_risk")
    assert market_scope.status == "classified"
    assert market_scope.version == NEWS_MARKET_SCOPE_VERSION


def test_crypto_scope_uses_token_mentions_and_accepted_facts() -> None:
    market_scope = _classify(
        item=_item(
            title="Coinbase lists BTC for trading",
            summary="The crypto exchange says Bitcoin trading starts today.",
            content_class="exchange_listing",
        ),
        token_mentions=[_mention("BTC", target_id="cex:BTC", resolution_status="known_symbol")],
        fact_candidates=[
            _fact(
                "exchange_listing",
                affected_targets=[{"target_type": "CexToken", "target_id": "cex:BTC"}],
            )
        ],
    )

    assert market_scope.primary == "crypto"
    assert market_scope.scope == ("crypto",)
    assert market_scope.basis["crypto_evidence"] == [
        "resolved_crypto_target:cex:BTC",
        "accepted_fact:exchange_listing",
        "text:crypto_subject",
    ]
    assert market_scope.to_payload() == {
        "scope": ["crypto"],
        "primary": "crypto",
        "status": "classified",
        "reason": "crypto_evidence",
        "basis": market_scope.basis,
        "version": NEWS_MARKET_SCOPE_VERSION,
    }


@pytest.mark.parametrize(
    ("item_overrides", "token_mentions", "fact_candidates", "match"),
    [
        pytest.param(
            {"coverage_tags_json": '["crypto"]'},
            [],
            [],
            "news_market_scope_coverage_tags_json_required",
            id="coverage_tags_string",
        ),
        pytest.param(
            {},
            [
                {
                    "observed_symbol": "BTC",
                    "display_symbol": "BTC",
                    "target_type": "CexToken",
                    "target_id": "cex:BTC",
                    "resolution_status": "known_symbol",
                    "reason_codes": "COMMON_WORD",
                    "market_type": "crypto",
                }
            ],
            [],
            "news_market_scope_reason_codes_required",
            id="reason_codes_string",
        ),
        pytest.param(
            {},
            [],
            [
                {
                    "event_type": "exchange_listing",
                    "validation_status": "accepted",
                    "affected_targets": '[{"target_type":"CexToken","target_id":"cex:BTC"}]',
                }
            ],
            "news_market_scope_affected_targets_required",
            id="affected_targets_string",
        ),
    ],
)
def test_market_scope_rejects_malformed_present_json_arrays(
    item_overrides: dict[str, object],
    token_mentions: list[Mapping[str, Any]],
    fact_candidates: list[Mapping[str, Any]],
    match: str,
) -> None:
    with pytest.raises(ValueError, match=match):
        _classify(
            item={**_item(title="Market scope test", summary="", content_class="low_signal"), **item_overrides},
            token_mentions=token_mentions,
            fact_candidates=fact_candidates,
        )


def _classify(
    *,
    item: Mapping[str, Any],
    token_mentions: list[Mapping[str, Any]] | None = None,
    fact_candidates: list[Mapping[str, Any]] | None = None,
) -> NewsMarketScope:
    return classify_news_market_scope(
        item=item,
        token_mentions=token_mentions or [],
        fact_candidates=fact_candidates or [],
    )


def _item(
    *,
    title: str,
    summary: str,
    content_class: str,
    body_text: str = "",
    source_domain: str = "example.com",
    source_name: str = "Example News",
    source_role: str = "specialist_media",
    coverage_tags: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "news_item_id": "news-1",
        "title": title,
        "summary": summary,
        "body_text": body_text,
        "content_class": content_class,
        "source_domain": source_domain,
        "source_name": source_name,
        "source_role": source_role,
        "coverage_tags_json": list(coverage_tags or []),
    }


def _mention(
    symbol: str,
    *,
    target_type: str = "CexToken",
    target_id: str | None,
    resolution_status: str,
    reason_codes: list[str] | None = None,
    market_type: str | None = None,
) -> dict[str, Any]:
    return {
        "observed_symbol": symbol,
        "display_symbol": symbol,
        "target_type": target_type,
        "target_id": target_id,
        "resolution_status": resolution_status,
        "reason_codes": list(reason_codes or []),
        "evidence_strength": "strong",
        "market_type": market_type,
    }


def _fact(
    event_type: str,
    *,
    affected_targets: list[Mapping[str, Any]] | None = None,
    validation_status: str = "accepted",
) -> dict[str, Any]:
    return {
        "event_type": event_type,
        "validation_status": validation_status,
        "affected_targets": list(affected_targets or []),
    }
