from __future__ import annotations

from typing import Any


def score_link(
    *,
    seed: dict[str, Any],
    identity_status: str,
    link_reason: str,
    matched_terms: list[str],
    mention_count: int,
    watched_mention_count: int,
    unique_author_count: int,
    top_author_share: float,
    market_status: str,
    market_cap: float | None,
    lag_ms: int,
) -> dict[str, Any]:
    seed_score, seed_reasons, seed_risks = _seed_score(seed)
    diffusion_score, diffusion_reasons, diffusion_risks = _diffusion_score(
        mention_count=mention_count,
        watched_mention_count=watched_mention_count,
        unique_author_count=unique_author_count,
        top_author_share=top_author_share,
    )
    token_link_score, link_reasons, link_risks = _token_link_score(
        identity_status=identity_status,
        link_reason=link_reason,
        matched_terms=matched_terms,
        lag_ms=lag_ms,
    )
    tradeability_score, trade_reasons, trade_risks = _tradeability_score(
        identity_status=identity_status,
        market_status=market_status,
        market_cap=market_cap,
    )
    risks = _dedupe([*seed_risks, *diffusion_risks, *link_risks, *trade_risks, "coverage_public_stream"])
    reasons = _dedupe([*seed_reasons, *diffusion_reasons, *link_reasons, *trade_reasons])
    return {
        "seed_score": seed_score,
        "diffusion_score": diffusion_score,
        "token_link_score": token_link_score,
        "tradeability_score": tradeability_score,
        "decision": _decision(
            identity_status=identity_status,
            market_status=market_status,
            market_cap=market_cap,
            seed_score=seed_score,
            diffusion_score=diffusion_score,
            token_link_score=token_link_score,
            tradeability_score=tradeability_score,
            risks=risks,
        ),
        "reasons": reasons,
        "risks": risks,
    }


def _seed_score(seed: dict[str, Any]) -> tuple[int, list[str], list[str]]:
    score = 30
    reasons = ["watched_handle_seed"]
    risks: list[str] = []
    if float(seed.get("source_weight") or 0.0) >= 0.75:
        score += 10
        reasons.append("source_weight_present")
    if float(seed.get("confidence") or 0.0) >= 0.75:
        score += 10
        reasons.append("high_narrative_confidence")
    if seed.get("intent") in {"technical_commentary", "macro_commentary", "meme", "trade_signal"}:
        score += 10
        reasons.append(str(seed.get("intent")))
    if seed.get("novelty_status") in {"new_global", "new_author"}:
        score += 10
        reasons.append(str(seed.get("novelty_status")))
    elif seed.get("novelty_status") == "repeat":
        score -= 15
        risks.append("repeat_seed")
    return _clamp(score), reasons, risks


def _diffusion_score(
    *,
    mention_count: int,
    watched_mention_count: int,
    unique_author_count: int,
    top_author_share: float,
) -> tuple[int, list[str], list[str]]:
    score = 0
    reasons: list[str] = []
    risks: list[str] = []
    if mention_count >= 1:
        score += 15
        reasons.append("post_seed_token_evidence")
    if watched_mention_count >= 1:
        score += 15
        reasons.append("watched_confirmation")
    if unique_author_count >= 2:
        score += 15
        reasons.append("multi_author")
    if unique_author_count >= 5:
        score += 15
        reasons.append("broad_source_spread")
    if top_author_share >= 0.75 and mention_count >= 3:
        score -= 20
        risks.append("author_concentration_high")
    return _clamp(score), reasons, risks


def _token_link_score(
    *,
    identity_status: str,
    link_reason: str,
    matched_terms: list[str],
    lag_ms: int,
) -> tuple[int, list[str], list[str]]:
    score = 0
    reasons = [link_reason]
    risks: list[str] = []
    if matched_terms:
        score += 30
        reasons.append("seed_terms_matched")
    if link_reason == "watched_seed_direct_token":
        score += 25
    elif link_reason == "seed_symbol_candidate_confirmed":
        score += 20
    elif link_reason == "name_or_alias_overlap":
        score += 15
    else:
        score += 10
    if identity_status == "resolved_ca":
        score += 20
        reasons.append("resolved_ca")
    else:
        score -= 15
        risks.append(identity_status)
    if lag_ms <= 15 * 60_000:
        score += 10
        reasons.append("fast_post_seed_link")
    return _clamp(score), reasons, risks


def _tradeability_score(
    *,
    identity_status: str,
    market_status: str,
    market_cap: float | None,
) -> tuple[int, list[str], list[str]]:
    score = 0
    reasons: list[str] = []
    risks: list[str] = []
    if identity_status == "resolved_ca":
        score += 35
        reasons.append("resolved_ca")
    else:
        risks.append(identity_status)
    if market_status == "fresh":
        score += 35
        reasons.append("fresh_market")
    elif market_status == "stale":
        score += 10
        risks.append("market_stale")
    else:
        risks.append("market_missing")
    if market_cap is not None:
        score += 20
        reasons.append("market_cap_present")
    else:
        risks.append("market_cap_missing")
    return _clamp(score), reasons, risks


def _decision(
    *,
    identity_status: str,
    market_status: str,
    market_cap: float | None,
    seed_score: int,
    diffusion_score: int,
    token_link_score: int,
    tradeability_score: int,
    risks: list[str],
) -> str:
    if identity_status in {"unresolved_symbol", "ambiguous_symbol", "unresolved_chain_ca"}:
        return "discard"
    if market_status == "missing" or market_cap is None:
        return "discard"
    if (
        seed_score >= 60
        and diffusion_score >= 45
        and token_link_score >= 65
        and tradeability_score >= 70
        and "author_concentration_high" not in risks
    ):
        return "driver"
    return "watch"


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _clamp(value: int) -> int:
    return max(0, min(100, value))
