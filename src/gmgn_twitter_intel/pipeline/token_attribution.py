from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any

SELECTED_CONFIDENCE = 0.70
SELECTED_MARGIN = 0.15
WEAK_CONFIDENCE = 0.45
SYMBOL_LOOKBACK_MS = 24 * 60 * 60_000


@dataclass(frozen=True, slots=True)
class TokenAttribution:
    attribution_id: str
    mention_id: str
    event_id: str
    mention_identity_key: str
    identity_key: str
    token_id: str | None
    identity_status: str
    chain: str | None
    address: str | None
    symbol: str
    source: str
    attribution_status: str
    attribution_confidence: float
    attribution_weight: float
    attribution_rank: int
    candidate_count: int
    score_features: dict[str, Any]
    reasons: list[str]
    risks: list[str]
    received_at_ms: int
    author_handle: str | None
    author_followers: int | None
    is_watched: bool


@dataclass(frozen=True, slots=True)
class _CandidateScore:
    token_id: str
    identity_key: str
    identity_status: str
    chain: str | None
    address: str | None
    symbol: str
    confidence: float
    score: float
    features: dict[str, Any]
    reasons: list[str]
    risks: list[str]


class TokenAttributionBuilder:
    def __init__(self, *, signals, tokens):
        self.signals = signals
        self.tokens = tokens

    def build_for_rows(self, rows: list[dict[str, Any]]) -> list[TokenAttribution]:
        attributions: list[TokenAttribution] = []
        for row in rows:
            attributions.extend(self.build_for_row(row))
        return attributions

    def build_for_row(self, row: dict[str, Any]) -> list[TokenAttribution]:
        if row.get("token_id"):
            return [self._direct_attribution(row)]
        symbol = _normalize_symbol(str(row.get("symbol") or ""))
        if not symbol:
            return [self._unresolved_attribution(row, reason="symbol_missing")]
        return self._symbol_attributions(row, symbol=symbol)

    def rebuild_symbol(self, symbol: str, *, commit: bool) -> list[TokenAttribution]:
        rows = self.signals.symbol_mention_rows(symbol=symbol)
        mention_ids = [str(row["mention_id"]) for row in rows]
        attributions = self.build_for_rows(rows)
        self.signals.replace_token_attributions(
            mention_ids=mention_ids,
            attributions=attributions,
            commit=commit,
        )
        return attributions

    def _direct_attribution(self, row: dict[str, Any]) -> TokenAttribution:
        token_id = str(row["token_id"])
        chain = row.get("chain")
        address = row.get("address")
        tradeable = _is_tradeable_chain(chain) and bool(address)
        status = "direct" if tradeable else "unresolved"
        confidence = 1.0 if tradeable else 0.0
        risks = [] if tradeable else ["untradeable_chain_or_address"]
        return self._attribution(
            row,
            identity_key=token_id,
            token_id=token_id if tradeable else None,
            identity_status=str(row.get("identity_status") or "resolved_ca"),
            chain=str(chain) if chain else None,
            address=str(address) if address else None,
            symbol=_normalize_symbol(str(row.get("symbol") or address or token_id)),
            source=str(row.get("source") or "event_token_mention"),
            attribution_status=status,
            confidence=confidence,
            weight=confidence,
            rank=1,
            candidate_count=1 if tradeable else 0,
            features={"identity": "direct_ca_or_payload"},
            reasons=["direct_token_identity"] if tradeable else [],
            risks=risks,
        )

    def _symbol_attributions(self, row: dict[str, Any], *, symbol: str) -> list[TokenAttribution]:
        candidate_ids = self.tokens.aliases_for_symbol(symbol)
        if not candidate_ids:
            return [self._unresolved_attribution(row, reason="symbol_has_no_token_candidates")]

        scores = [self._score_candidate(row, symbol=symbol, token_id=token_id) for token_id in candidate_ids]
        scores = [score for score in scores if score is not None]
        if not scores:
            return [self._unresolved_attribution(row, reason="symbol_candidates_missing_token_rows")]
        scores.sort(key=lambda item: (item.score, item.confidence, item.token_id), reverse=True)
        top = scores[0]
        runner = scores[1] if len(scores) > 1 else None
        margin = top.score - (runner.score if runner else 0.0)
        selected = _selected_symbol_candidate(top, runner=runner, margin=margin)
        status_for_unselected = "ambiguous" if len(scores) > 1 else "weak_candidate"

        attributions: list[TokenAttribution] = []
        for rank, score in enumerate(scores, start=1):
            is_selected = selected and rank == 1
            reasons = list(score.reasons)
            risks = list(score.risks)
            if runner and rank == 1:
                reasons.extend(_lead_reasons(score.features, runner.features))
            if is_selected:
                reasons.append("symbol_candidate_selected")
                status = "selected"
                confidence = _selected_confidence(score, single_candidate=runner is None)
                weight = confidence
            else:
                if status_for_unselected == "ambiguous":
                    risks.append("symbol_candidate_margin_too_close")
                elif score.confidence < WEAK_CONFIDENCE:
                    risks.append("symbol_candidate_confidence_low")
                status = "rejected" if selected else status_for_unselected
                confidence = score.confidence
                weight = 0.0
            features = {
                **score.features,
                "candidate_score": score.score,
                "candidate_margin": margin if rank == 1 else None,
                "selected_threshold": SELECTED_CONFIDENCE,
                "margin_threshold": SELECTED_MARGIN,
            }
            attributions.append(
                self._attribution(
                    row,
                    identity_key=score.identity_key,
                    token_id=score.token_id,
                    identity_status=score.identity_status,
                    chain=score.chain,
                    address=score.address,
                    symbol=score.symbol,
                    source=str(row.get("source") or "cashtag"),
                    attribution_status=status,
                    confidence=confidence,
                    weight=weight,
                    rank=rank,
                    candidate_count=len(scores),
                    features=features,
                    reasons=_dedupe(reasons),
                    risks=_dedupe(risks),
                )
            )
        return attributions

    def _score_candidate(self, row: dict[str, Any], *, symbol: str, token_id: str) -> _CandidateScore | None:
        token = self.tokens.get_token(token_id)
        if token is None:
            return None
        snapshot = self.tokens.market_snapshot_at_or_before(token_id, int(row["received_at_ms"]))
        snapshot_after_mention = False
        if snapshot is None:
            snapshot = self.tokens.latest_market_snapshot(token_id)
            snapshot_after_mention = snapshot is not None
        raw = _raw_snapshot(snapshot)
        market_cap = _float_or_none(snapshot.get("market_cap")) if snapshot else None
        liquidity = _first_number(raw, ["liquidity", "liquidity_usd", "pool.liquidity", "pool.liquidity_usd"])
        holder_count = _first_number(raw, ["holder_count", "holders", "holder"])
        volume_24h = _first_number(raw, ["volume_24h", "volume", "stat.volume_24h", "stat.volume"])
        pool_address = _first_string(raw, ["pool.pool_address", "pool.address", "pool"])
        snapshot_age_ms = (
            max(0, int(row["received_at_ms"]) - int(snapshot["received_at_ms"]))
            if snapshot is not None
            else None
        )
        direct_mentions_24h = self.signals.direct_token_mention_count(
            token_id=token_id,
            since_ms=int(row["received_at_ms"]) - SYMBOL_LOOKBACK_MS,
            before_ms=int(row["received_at_ms"]) + 1,
        )

        identity_score = 0.80
        market_score = _log_score(market_cap, low=10_000, high=50_000_000)
        liquidity_score = _log_score(liquidity, low=5_000, high=2_000_000)
        holder_score = _log_score(holder_count, low=100, high=50_000)
        volume_score = _log_score(volume_24h, low=10_000, high=5_000_000)
        activity_score = max(holder_score, volume_score)
        social_score = min(1.0, direct_mentions_24h / 3)
        recency_score = _recency_score(snapshot_age_ms)
        pool_score = 1.0 if pool_address else 0.0

        risk_penalty = 0.0
        risks: list[str] = []
        reasons: list[str] = ["symbol_alias_candidate"]
        if market_cap is None:
            risks.append("market_cap_missing")
            risk_penalty += 0.20
        else:
            reasons.append("market_cap_present")
        if liquidity is None:
            risks.append("liquidity_missing")
            risk_penalty += 0.10
        elif liquidity < 5_000:
            risks.append("liquidity_low")
            risk_penalty += 0.15
        else:
            reasons.append("liquidity_present")
        if pool_address:
            reasons.append("pool_present")
        else:
            risks.append("pool_missing")
            risk_penalty += 0.05
        if snapshot_age_ms is None:
            risks.append("market_snapshot_missing")
            risk_penalty += 0.20
        elif snapshot_after_mention:
            reasons.append("post_evidence_market_snapshot")
        elif snapshot_age_ms <= SYMBOL_LOOKBACK_MS:
            reasons.append("fresh_market_snapshot")
        else:
            risks.append("market_snapshot_stale")
            risk_penalty += 0.10

        score = (
            0.15 * identity_score
            + 0.30 * market_score
            + 0.15 * liquidity_score
            + 0.05 * pool_score
            + 0.15 * activity_score
            + 0.10 * social_score
            + 0.10 * recency_score
            - risk_penalty
        )
        score = _clamp(score)
        confidence = _clamp(0.35 + 0.55 * score)
        features = {
            "identity_score": identity_score,
            "market_score": market_score,
            "liquidity_score": liquidity_score,
            "pool_score": pool_score,
            "activity_score": activity_score,
            "social_score": social_score,
            "recency_score": recency_score,
            "risk_penalty": risk_penalty,
            "market_cap": market_cap,
            "liquidity": liquidity,
            "holder_count": holder_count,
            "volume_24h": volume_24h,
            "pool_address": pool_address,
            "snapshot_age_ms": snapshot_age_ms,
            "snapshot_after_mention": snapshot_after_mention,
            "direct_mentions_24h": direct_mentions_24h,
        }
        return _CandidateScore(
            token_id=str(token["token_id"]),
            identity_key=str(token["token_id"]),
            identity_status=str(token.get("identity_status") or "resolved_ca"),
            chain=token.get("chain"),
            address=token.get("address"),
            symbol=_normalize_symbol(str(token.get("symbol") or symbol)),
            confidence=confidence,
            score=score,
            features=features,
            reasons=reasons,
            risks=risks,
        )

    def _unresolved_attribution(self, row: dict[str, Any], *, reason: str) -> TokenAttribution:
        return self._attribution(
            row,
            identity_key=str(row.get("identity_key") or f"symbol:{row.get('symbol')}"),
            token_id=None,
            identity_status=str(row.get("identity_status") or "unresolved_symbol"),
            chain=None,
            address=None,
            symbol=_normalize_symbol(str(row.get("symbol") or "UNKNOWN")),
            source=str(row.get("source") or "event_token_mention"),
            attribution_status="unresolved",
            confidence=0.0,
            weight=0.0,
            rank=1,
            candidate_count=0,
            features={},
            reasons=[],
            risks=[reason],
        )

    def _attribution(
        self,
        row: dict[str, Any],
        *,
        identity_key: str,
        token_id: str | None,
        identity_status: str,
        chain: str | None,
        address: str | None,
        symbol: str,
        source: str,
        attribution_status: str,
        confidence: float,
        weight: float,
        rank: int,
        candidate_count: int,
        features: dict[str, Any],
        reasons: list[str],
        risks: list[str],
    ) -> TokenAttribution:
        mention_id = str(row["mention_id"])
        return TokenAttribution(
            attribution_id=_id("token_attribution", mention_id, str(rank)),
            mention_id=mention_id,
            event_id=str(row["event_id"]),
            mention_identity_key=str(row["identity_key"]),
            identity_key=identity_key,
            token_id=token_id,
            identity_status=identity_status,
            chain=chain,
            address=address,
            symbol=symbol,
            source=source,
            attribution_status=attribution_status,
            attribution_confidence=round(float(confidence), 6),
            attribution_weight=round(float(weight), 6),
            attribution_rank=rank,
            candidate_count=candidate_count,
            score_features=features,
            reasons=reasons,
            risks=risks,
            received_at_ms=int(row["received_at_ms"]),
            author_handle=row.get("author_handle"),
            author_followers=row.get("author_followers"),
            is_watched=bool(row.get("is_watched")),
        )


def _lead_reasons(top: dict[str, Any], runner: dict[str, Any]) -> list[str]:
    reasons = []
    if float(top.get("market_score") or 0.0) - float(runner.get("market_score") or 0.0) >= 0.20:
        reasons.append("market_quality_lead")
    if float(top.get("liquidity_score") or 0.0) - float(runner.get("liquidity_score") or 0.0) >= 0.20:
        reasons.append("liquidity_lead")
    if float(top.get("activity_score") or 0.0) - float(runner.get("activity_score") or 0.0) >= 0.20:
        reasons.append("activity_lead")
    if float(top.get("social_score") or 0.0) - float(runner.get("social_score") or 0.0) >= 0.20:
        reasons.append("direct_evidence_lead")
    return reasons


def _selected_symbol_candidate(score: _CandidateScore, *, runner: _CandidateScore | None, margin: float) -> bool:
    hard_risks = {"market_snapshot_missing", "market_cap_missing", "liquidity_missing", "pool_missing"}
    if set(score.risks) & hard_risks:
        return False
    if runner is None:
        return score.confidence >= WEAK_CONFIDENCE
    return score.confidence >= SELECTED_CONFIDENCE and margin >= SELECTED_MARGIN


def _selected_confidence(score: _CandidateScore, *, single_candidate: bool) -> float:
    if single_candidate:
        return max(score.confidence, 0.75)
    return score.confidence


def _raw_snapshot(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    if not snapshot:
        return {}
    raw_json = snapshot.get("raw_json")
    if not isinstance(raw_json, str):
        return {}
    try:
        raw = json.loads(raw_json)
    except json.JSONDecodeError:
        return {}
    return raw if isinstance(raw, dict) else {}


def _first_number(raw: dict[str, Any], paths: list[str]) -> float | None:
    for path in paths:
        value = _path_value(raw, path)
        number = _float_or_none(value)
        if number is not None:
            return number
    return None


def _first_string(raw: dict[str, Any], paths: list[str]) -> str | None:
    for path in paths:
        value = _path_value(raw, path)
        if isinstance(value, dict):
            continue
        if value is not None:
            text = str(value).strip()
            if text:
                return text
    return None


def _path_value(raw: dict[str, Any], path: str) -> Any:
    current: Any = raw
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _log_score(value: Any, *, low: float, high: float) -> float:
    number = _float_or_none(value)
    if number is None or number <= 0:
        return 0.0
    low_log = math.log10(low)
    high_log = math.log10(high)
    value_log = math.log10(max(low, min(high, number)))
    return _clamp((value_log - low_log) / (high_log - low_log))


def _recency_score(age_ms: int | None) -> float:
    if age_ms is None:
        return 0.0
    if age_ms <= 30 * 60_000:
        return 1.0
    if age_ms >= SYMBOL_LOOKBACK_MS:
        return 0.0
    return _clamp(1.0 - (age_ms / SYMBOL_LOOKBACK_MS))


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_tradeable_chain(chain: Any) -> bool:
    return bool(chain) and str(chain) not in {"unknown", "evm", "evm_unknown"}


def _normalize_symbol(symbol: str) -> str:
    text = symbol.strip().lstrip("$")
    return text.upper() if text.isascii() else text


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
