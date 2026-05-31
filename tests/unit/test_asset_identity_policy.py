from __future__ import annotations

from parallax.domains.asset_market.identity_evidence_policy import (
    CONFIDENCE_PROVIDER_CANDIDATE,
    CONFIDENCE_PROVIDER_EXACT,
    EVIDENCE_GMGN_PAYLOAD_EXACT,
    EVIDENCE_OKX_DEX_EXACT_ADDRESS,
    EVIDENCE_OKX_DEX_SYMBOL_CANDIDATE,
    EVIDENCE_TWEET_CONTRACT_MENTION,
    select_current_identity,
)

ASSET_ID = "asset:eip155:1:erc20:0x999b49c0d1612e619a4a4f6280733184da025108"


def evidence(
    *,
    evidence_id: str,
    evidence_kind: str,
    symbol: str | None,
    name: str | None = None,
    observed_at_ms: int,
    provider: str = "test",
    lookup_mode: str = "test",
):
    return {
        "evidence_id": evidence_id,
        "asset_id": ASSET_ID,
        "evidence_kind": evidence_kind,
        "provider": provider,
        "lookup_mode": lookup_mode,
        "symbol": symbol,
        "name": name,
        "decimals": None,
        "observed_at_ms": observed_at_ms,
    }


def test_exact_address_identity_wins_over_tweet_mention_and_symbol_candidate():
    current = select_current_identity(
        asset_id=ASSET_ID,
        evidence_rows=[
            evidence(
                evidence_id="tweet-sato",
                evidence_kind=EVIDENCE_TWEET_CONTRACT_MENTION,
                symbol="SATO",
                observed_at_ms=100,
            ),
            evidence(
                evidence_id="okx-symbol-candidate",
                evidence_kind=EVIDENCE_OKX_DEX_SYMBOL_CANDIDATE,
                symbol="SPEC",
                observed_at_ms=200,
            ),
            evidence(
                evidence_id="okx-exact",
                evidence_kind=EVIDENCE_OKX_DEX_EXACT_ADDRESS,
                symbol="SLOP",
                name="SLOP",
                observed_at_ms=150,
            ),
        ],
        now_ms=1_000,
    )

    assert current["canonical_symbol"] == "SLOP"
    assert current["canonical_name"] == "SLOP"
    assert current["identity_confidence"] == CONFIDENCE_PROVIDER_EXACT
    assert current["selected_evidence_id"] == "okx-exact"
    assert "SELECTED_PROVIDER_EXACT" in current["selection_reason_codes"]
    assert "MENTION_NOT_CANONICAL" in current["selection_reason_codes"]
    assert current["conflict_count"] == 2


def test_newest_wins_only_inside_same_evidence_kind():
    current = select_current_identity(
        asset_id=ASSET_ID,
        evidence_rows=[
            evidence(
                evidence_id="gmgn-old",
                evidence_kind=EVIDENCE_GMGN_PAYLOAD_EXACT,
                symbol="SLOP",
                observed_at_ms=100,
            ),
            evidence(
                evidence_id="gmgn-new",
                evidence_kind=EVIDENCE_GMGN_PAYLOAD_EXACT,
                symbol="SLOP2",
                observed_at_ms=200,
            ),
            evidence(
                evidence_id="candidate-newer",
                evidence_kind=EVIDENCE_OKX_DEX_SYMBOL_CANDIDATE,
                symbol="SPEC",
                observed_at_ms=300,
            ),
        ],
        now_ms=1_000,
    )

    assert current["canonical_symbol"] == "SLOP2"
    assert current["identity_confidence"] == CONFIDENCE_PROVIDER_EXACT
    assert current["selected_evidence_id"] == "gmgn-new"


def test_symbol_candidate_is_candidate_identity_when_no_exact_evidence_exists():
    current = select_current_identity(
        asset_id=ASSET_ID,
        evidence_rows=[
            evidence(
                evidence_id="tweet-sato",
                evidence_kind=EVIDENCE_TWEET_CONTRACT_MENTION,
                symbol="SATO",
                observed_at_ms=100,
            ),
            evidence(
                evidence_id="candidate-spec",
                evidence_kind=EVIDENCE_OKX_DEX_SYMBOL_CANDIDATE,
                symbol="SPEC",
                observed_at_ms=200,
            ),
        ],
        now_ms=1_000,
    )

    assert current["canonical_symbol"] == "SPEC"
    assert current["identity_confidence"] == CONFIDENCE_PROVIDER_CANDIDATE
    assert current["selected_evidence_id"] == "candidate-spec"
    assert "SELECTED_PROVIDER_CANDIDATE" in current["selection_reason_codes"]
    assert "MENTION_NOT_CANONICAL" in current["selection_reason_codes"]
