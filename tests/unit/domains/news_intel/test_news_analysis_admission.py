from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from parallax.domains.news_intel._constants import NEWS_ANALYSIS_ADMISSION_VERSION
from parallax.domains.news_intel.services.news_analysis_admission import (
    NewsAnalysisAdmission,
    decide_news_analysis_admission,
)


def test_spacex_private_company_is_page_only_even_with_spcx_provider_impacts() -> None:
    admission = _decide(
        item=_item(
            title="SpaceX expands Starship launch cadence after private funding round",
            summary="The private space company is not publicly traded.",
            content_class="low_signal",
            provider_token_impacts_json=[{"symbol": "SPCX", "market_type": "crypto", "score": 91}],
        ),
        token_mentions=[
            _mention(
                "SPCX",
                target_id="cex:SPCX",
                resolution_status="unique_by_context",
                reason_codes=["PRIVATE_COMPANY_SYMBOL_COLLISION"],
            )
        ],
    )

    assert admission.status == "page_only"
    assert admission.reason == "non_crypto_subject"
    assert admission.version == NEWS_ANALYSIS_ADMISSION_VERSION
    assert "PRIVATE_COMPANY_SYMBOL_COLLISION" in admission.basis["negative_evidence"]


def test_samsung_equity_share_headline_is_page_only() -> None:
    admission = _decide(
        item=_item(
            title="Samsung Electronics shares climb after memory chip outlook improves",
            summary="The Korea-listed equity gained as analysts raised estimates.",
            content_class="ai_semiconductors",
        ),
        token_mentions=[
            _mention(
                "SSNLF",
                target_type="MarketInstrument",
                target_id="equity:SSNLF",
                resolution_status="non_crypto",
                market_type="equity",
            )
        ],
    )

    assert admission.status == "page_only"
    assert admission.reason == "non_crypto_subject"


def test_dram_hard_drive_story_does_not_admit_fil_from_symbol_collision() -> None:
    admission = _decide(
        item=_item(
            title="DRAM and hard drive suppliers lift guidance as file storage demand rebounds",
            summary="Analysts cite enterprise hard drive inventory normalization.",
            content_class="ai_semiconductors",
            provider_token_impacts_json=[{"symbol": "FIL", "market_type": "crypto", "score": 86}],
        ),
        token_mentions=[
            _mention(
                "FIL",
                target_id="cex:FIL",
                resolution_status="unique_by_context",
                reason_codes=["COMMON_WORD_SYMBOL_COLLISION"],
            )
        ],
    )

    assert admission.status == "page_only"
    assert admission.reason == "non_crypto_subject"
    assert "COMMON_WORD_SYMBOL_COLLISION" in admission.basis["negative_evidence"]


def test_hormuz_oil_geopolitics_is_research_context_not_crypto_driver() -> None:
    admission = _decide(
        item=_item(
            title="Oil jumps as Hormuz shipping risks rise after Middle East escalation",
            summary="Crude traders price geopolitical risk and possible supply disruption.",
            content_class="energy_geopolitics",
        )
    )

    assert admission.status == "research_context"
    assert admission.reason == "macro_context_without_crypto_fact"


def test_zcash_orchard_bug_is_admitted_security_event() -> None:
    admission = _decide(
        item=_item(
            title="Zcash discloses Orchard shielded pool bug and ships emergency fix",
            summary="The protocol says no funds were lost in the security incident.",
            content_class="security_hack",
        ),
        token_mentions=[_mention("ZEC", target_id="cex:ZEC", resolution_status="known_symbol")],
        fact_candidates=[
            _fact(
                "security_incident",
                affected_targets=[{"target_type": "CexToken", "target_id": "cex:ZEC"}],
            )
        ],
    )

    assert admission.status == "admitted"
    assert admission.reason == "crypto_native_evidence"


def test_jpm_citi_tokenized_deposit_story_is_admitted_crypto_market() -> None:
    admission = _decide(
        item=_item(
            title="JPMorgan and Citi test tokenized deposit settlement network",
            summary="Banks trial blockchain rails for tokenized commercial deposits.",
            content_class="crypto_market",
        )
    )

    assert admission.status == "admitted"
    assert admission.reason == "crypto_native_evidence"
    assert "text:crypto_subject" in admission.basis["crypto_evidence"]


def test_coinbase_btc_mortgage_score_70_is_admitted_with_crypto_subject() -> None:
    admission = _decide(
        item=_item(
            title="Coinbase launches BTC-backed mortgage pilot for US borrowers",
            summary="The crypto exchange said customers can pledge Bitcoin collateral.",
            content_class="crypto_market",
            provider_signal_json={"source": "provider", "score": 70},
            provider_token_impacts_json=[{"symbol": "BTC", "market_type": "crypto", "score": 70}],
        ),
        token_mentions=[_mention("BTC", target_id="cex:BTC", resolution_status="known_symbol")],
    )

    assert admission.status == "admitted"
    assert admission.reason == "crypto_native_evidence"
    assert "provider_score:70" in admission.basis["provider_evidence"]


def test_common_word_symbols_do_not_create_crypto_admission() -> None:
    admission = _decide(
        item=_item(
            title="Shipping company moves a ton of cargo through new port terminal",
            summary="The common word appears in ordinary logistics context.",
            content_class="low_signal",
        ),
        token_mentions=[
            _mention(
                "TON",
                target_id="cex:TON",
                resolution_status="unique_by_context",
                reason_codes=["COMMON_WORD_SYMBOL_COLLISION"],
            )
        ],
    )

    assert admission.status == "page_only"
    assert admission.reason == "non_crypto_subject"


def test_process_worker_payload_reason_codes_collision_remains_page_only() -> None:
    admission = _decide(
        item=_item(
            title="Company says ton of export volume rose in May",
            summary="The logistics update uses TON as a common word, not a token.",
            content_class="low_signal",
        ),
        token_mentions=[
            _mention(
                "TON",
                target_id="cex:TON",
                resolution_status="unique_by_context",
                reason_codes=["COMMON_WORD_SYMBOL_COLLISION"],
            )
        ],
    )

    assert admission.status == "page_only"
    assert admission.reason == "non_crypto_subject"


def test_process_worker_payload_affected_targets_accepted_crypto_fact_admits() -> None:
    admission = _decide(
        item=_item(
            title="Protocol discloses consensus incident and emergency fix",
            summary="Maintainers shipped a patch after the incident.",
            content_class="security_hack",
        ),
        fact_candidates=[
            _fact(
                "security_incident",
                affected_targets=[{"target_type": "Asset", "target_id": "asset:base:0xabc"}],
            )
        ],
    )

    assert admission.status == "admitted"
    assert admission.reason == "crypto_native_evidence"


def test_persisted_row_payload_reason_codes_json_collision_blocks_admission() -> None:
    admission = _decide(
        item=_item(
            title="Company says ton of export volume rose in May",
            summary="The logistics update uses TON as a common word, not a crypto asset.",
            content_class="low_signal",
        ),
        token_mentions=[
            _persisted_mention(
                "TON",
                target_id="cex:TON",
                resolution_status="unique_by_context",
                reason_codes_json=["COMMON_WORD_SYMBOL_COLLISION"],
            )
        ],
    )

    assert admission.status == "page_only"
    assert admission.reason == "non_crypto_subject"
    assert "COMMON_WORD_SYMBOL_COLLISION" in admission.basis["negative_evidence"]


def test_persisted_row_payload_affected_targets_json_accepted_crypto_fact_admits() -> None:
    admission = _decide(
        item=_item(
            title="Protocol discloses consensus incident and emergency fix",
            summary="Maintainers shipped a patch after the incident.",
            content_class="security_hack",
        ),
        fact_candidates=[
            _persisted_fact(
                "security_incident",
                affected_targets_json=[{"target_type": "Asset", "target_id": "asset:base:0xabc"}],
            )
        ],
    )

    assert admission.status == "admitted"
    assert admission.reason == "crypto_native_evidence"


def test_energy_row_with_accepted_crypto_fact_is_not_research_context() -> None:
    admission = _decide(
        item=_item(
            title="Oil shock hits exchange token collateral pool during liquidation event",
            summary="The energy move triggered a protocol-level liquidation incident.",
            content_class="energy_geopolitics",
        ),
        fact_candidates=[
            _fact(
                "security_incident",
                affected_targets=[{"target_type": "CexToken", "target_id": "cex:BTC"}],
            )
        ],
    )

    assert admission.status == "admitted"
    assert admission.reason == "crypto_native_evidence"


def test_rates_fed_with_resolved_btc_token_mention_admits_not_research_context() -> None:
    admission = _decide(
        item=_item(
            title="Fed decision jolts liquidity expectations",
            summary="Macro traders reassessed the path for risk assets.",
            content_class="rates_fed",
        ),
        token_mentions=[_mention("BTC", target_id="cex:BTC", resolution_status="known_symbol")],
    )

    assert admission.status == "admitted"
    assert admission.reason == "crypto_native_evidence"


def test_energy_geopolitics_with_outside_crypto_market_type_is_page_only_not_research_context() -> None:
    admission = _decide(
        item=_item(
            title="Oil jumps as Hormuz shipping risks rise",
            summary="Crude traders price geopolitical risk and possible supply disruption.",
            content_class="energy_geopolitics",
        ),
        token_mentions=[
            _mention(
                "OIL",
                target_type="MarketInstrument",
                target_id="commodity:oil",
                resolution_status="non_crypto",
                market_type="commodity",
            )
        ],
    )

    assert admission.status == "page_only"
    assert admission.reason == "non_crypto_subject"


def test_source_domain_and_name_crypto_subject_can_admit_allowed_content_class() -> None:
    admission = _decide(
        item=_item(
            title="New collateral pilot opens to borrowers",
            summary="Customers can pledge assets through the new product.",
            content_class="crypto_market",
            source_domain="coinbase.com",
            source_name="Coinbase Blog",
            source_role="official_exchange",
            coverage_tags=["crypto"],
        )
    )

    assert admission.status == "admitted"
    assert admission.reason == "crypto_native_evidence"
    assert "text:crypto_subject" in admission.basis["crypto_evidence"]


def _decide(
    *,
    item: Mapping[str, Any],
    token_mentions: list[Mapping[str, Any]] | None = None,
    fact_candidates: list[Mapping[str, Any]] | None = None,
) -> NewsAnalysisAdmission:
    return decide_news_analysis_admission(
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
    provider_signal_json: Mapping[str, Any] | None = None,
    provider_token_impacts_json: list[Mapping[str, Any]] | None = None,
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
        "provider_signal_json": dict(provider_signal_json or {}),
        "provider_token_impacts_json": list(provider_token_impacts_json or []),
        "source_domain": source_domain,
        "source_name": source_name,
        "source_role": source_role,
        "coverage_tags_json": list(coverage_tags or []),
        "source_policy_status": "enabled",
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


def _persisted_mention(
    symbol: str,
    *,
    target_type: str = "CexToken",
    target_id: str | None,
    resolution_status: str,
    reason_codes_json: list[str] | None = None,
    market_type: str | None = None,
) -> dict[str, Any]:
    return {
        "observed_symbol": symbol,
        "display_symbol": symbol,
        "target_type": target_type,
        "target_id": target_id,
        "resolution_status": resolution_status,
        "reason_codes_json": list(reason_codes_json or []),
        "evidence_strength": "strong",
        "market_type": market_type,
    }


def _fact(
    event_type: str,
    *,
    validation_status: str = "accepted",
    affected_targets: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "event_type": event_type,
        "validation_status": validation_status,
        "affected_targets": list(affected_targets or []),
    }


def _persisted_fact(
    event_type: str,
    *,
    validation_status: str = "accepted",
    affected_targets_json: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "event_type": event_type,
        "validation_status": validation_status,
        "affected_targets_json": list(affected_targets_json or []),
    }
