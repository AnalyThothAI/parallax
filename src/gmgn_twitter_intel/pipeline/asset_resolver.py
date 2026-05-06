from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ..storage.asset_repository import AssetRepository

MARKET_REFRESH_STALE_MS = 5 * 60 * 1000


@dataclass(frozen=True, slots=True)
class AssetResolutionDecision:
    mention_id: str
    event_id: str
    asset_id: str
    venue_id: str | None
    attribution_status: str
    identity_status: str
    confidence: float
    attribution_weight: float
    reasons: list[str]
    risks: list[str]


class AssetResolver:
    def __init__(self, assets: AssetRepository):
        self.assets = assets

    def resolve_many(self, mentions: list[Mapping[str, Any]]) -> list[AssetResolutionDecision]:
        return [self.resolve(mention) for mention in mentions]

    def resolve(self, mention: Mapping[str, Any]) -> AssetResolutionDecision:
        mention_type = str(mention.get("mention_type") or "")
        if mention_type == "gmgn_payload":
            direct = self._resolve_direct_dex(mention, reason="gmgn_payload_direct")
            if direct is not None:
                return direct

        if mention_type == "ca":
            return self._resolve_ca(mention)

        symbol = _symbol(mention)
        if symbol:
            return self._resolve_symbol(mention, symbol=symbol)

        asset = self.assets.upsert_unresolved_ca(
            str(mention.get("raw_value") or ""),
            event_id=_event_id(mention),
            observed_at_ms=_created_at_ms(mention),
            commit=False,
        )
        return self._decision(
            mention,
            asset_id=str(asset["asset_id"]),
            venue_id=None,
            attribution_status="unresolved",
            identity_status="unresolved",
            confidence=0.1,
            attribution_weight=0.5,
            reasons=["mention_has_no_symbol_or_address"],
            risks=[],
        )

    def _resolve_ca(self, mention: Mapping[str, Any]) -> AssetResolutionDecision:
        direct = self._resolve_direct_dex(mention, reason="ca_with_chain_hint")
        if direct is not None:
            return direct
        address = str(mention.get("address_hint") or mention.get("raw_value") or "")
        asset = self.assets.upsert_unresolved_ca(
            address,
            event_id=_event_id(mention),
            observed_at_ms=_created_at_ms(mention),
            chain_hint=_clean_text(mention.get("chain_hint")),
            commit=False,
        )
        self.assets.queue_resolution_job(
            job_type="ca_resolution",
            chain_hint=_clean_text(mention.get("chain_hint")),
            address_hint=address,
            next_run_at_ms=_created_at_ms(mention),
            commit=False,
        )
        return self._decision(
            mention,
            asset_id=str(asset["asset_id"]),
            venue_id=None,
            attribution_status="unresolved",
            identity_status="unresolved",
            confidence=0.35,
            attribution_weight=0.8,
            reasons=["ca_missing_chain_hint"],
            risks=[],
        )

    def _resolve_symbol(self, mention: Mapping[str, Any], *, symbol: str) -> AssetResolutionDecision:
        candidates = self.assets.candidates_for_symbol(symbol)
        asset_candidates = _unique_asset_candidates(_real_asset_candidates(candidates))
        cex_candidates = [candidate for candidate in asset_candidates if candidate.get("venue_type") == "cex"]
        if len(cex_candidates) == 1:
            candidate = cex_candidates[0]
            return self._decision(
                mention,
                asset_id=str(candidate["asset_id"]),
                venue_id=candidate.get("venue_id"),
                attribution_status="selected",
                identity_status=str(candidate.get("identity_status") or "resolved"),
                confidence=float(candidate.get("asset_confidence") or candidate.get("alias_confidence") or 0.85),
                attribution_weight=1.0,
                reasons=["single_local_cex_asset_candidate"],
                risks=[],
            )
        if not asset_candidates:
            asset = self.assets.upsert_unresolved_symbol(
                symbol,
                event_id=_event_id(mention),
                observed_at_ms=_created_at_ms(mention),
                commit=False,
            )
            self._queue_symbol_resolution(symbol, mention)
            return self._decision(
                mention,
                asset_id=str(asset["asset_id"]),
                venue_id=None,
                attribution_status="unresolved",
                identity_status="unresolved",
                confidence=0.25,
                attribution_weight=1.0,
                reasons=["symbol_has_no_candidates"],
                risks=[],
            )

        if len(asset_candidates) == 1:
            candidate = asset_candidates[0]
            self._queue_dex_market_refresh_if_stale(candidate, mention)
            return self._decision(
                mention,
                asset_id=str(candidate["asset_id"]),
                venue_id=candidate.get("venue_id"),
                attribution_status="selected",
                identity_status=str(candidate.get("identity_status") or "resolved"),
                confidence=float(candidate.get("asset_confidence") or candidate.get("alias_confidence") or 0.75),
                attribution_weight=1.0,
                reasons=["single_local_asset_candidate"],
                risks=[],
            )

        asset = self.assets.upsert_ambiguous_symbol(
            symbol,
            event_id=_event_id(mention),
            observed_at_ms=_created_at_ms(mention),
            commit=False,
        )
        self._queue_symbol_resolution(symbol, mention)
        return self._decision(
            mention,
            asset_id=str(asset["asset_id"]),
            venue_id=None,
            attribution_status="ambiguous",
            identity_status="ambiguous",
            confidence=0.5,
            attribution_weight=1.0,
            reasons=["multiple_local_asset_candidates"],
            risks=["candidate_selection_requires_provider_resolution"],
        )

    def _queue_symbol_resolution(self, symbol: str, mention: Mapping[str, Any]) -> None:
        self.assets.queue_resolution_job(
            job_type="symbol_resolution",
            normalized_symbol=symbol,
            next_run_at_ms=_created_at_ms(mention),
            commit=False,
        )

    def _resolve_direct_dex(self, mention: Mapping[str, Any], *, reason: str) -> AssetResolutionDecision | None:
        chain = _clean_text(mention.get("chain_hint"))
        address = _clean_text(mention.get("address_hint"))
        if not chain or not address:
            return None
        symbol = _symbol(mention) or address
        result = self.assets.upsert_dex_asset(
            chain=chain,
            address=address,
            symbol=symbol,
            event_id=_event_id(mention),
            observed_at_ms=_created_at_ms(mention),
            provider="gmgn" if reason == "gmgn_payload_direct" else "deterministic",
            commit=False,
        )
        venue = result.venue or {}
        if reason != "gmgn_payload_direct":
            self._queue_dex_market_refresh(
                asset_id=str(result.asset["asset_id"]),
                chain=_clean_text(venue.get("chain")) or chain,
                address=_clean_text(venue.get("address")) or address,
                mention=mention,
            )
        return self._decision(
            mention,
            asset_id=str(result.asset["asset_id"]),
            venue_id=str(result.venue["venue_id"]) if result.venue else None,
            attribution_status="direct",
            identity_status="resolved",
            confidence=1.0,
            attribution_weight=1.0,
            reasons=[reason],
            risks=[],
        )

    def _queue_dex_market_refresh_if_stale(self, candidate: Mapping[str, Any], mention: Mapping[str, Any]) -> None:
        if candidate.get("venue_type") != "dex":
            return
        self._queue_dex_market_refresh(
            asset_id=str(candidate.get("asset_id") or ""),
            chain=_clean_text(candidate.get("chain")),
            address=_clean_text(candidate.get("address")),
            mention=mention,
        )

    def _queue_dex_market_refresh(
        self,
        *,
        asset_id: str,
        chain: str | None,
        address: str | None,
        mention: Mapping[str, Any],
    ) -> None:
        if not asset_id or not chain or not address:
            return
        decision_time_ms = _created_at_ms(mention)
        latest = self.assets.market_snapshot_at_or_before(asset_id, decision_time_ms)
        if latest is not None and decision_time_ms - int(latest.get("observed_at_ms") or 0) < MARKET_REFRESH_STALE_MS:
            return
        self.assets.queue_resolution_job(
            job_type="ca_resolution",
            chain_hint=chain,
            address_hint=address,
            next_run_at_ms=decision_time_ms,
            commit=False,
        )

    def _decision(
        self,
        mention: Mapping[str, Any],
        *,
        asset_id: str,
        venue_id: str | None,
        attribution_status: str,
        identity_status: str,
        confidence: float,
        attribution_weight: float,
        reasons: list[str],
        risks: list[str],
    ) -> AssetResolutionDecision:
        return AssetResolutionDecision(
            mention_id=str(mention["mention_id"]),
            event_id=_event_id(mention),
            asset_id=asset_id,
            venue_id=venue_id,
            attribution_status=attribution_status,
            identity_status=identity_status,
            confidence=confidence,
            attribution_weight=attribution_weight,
            reasons=reasons,
            risks=risks,
        )


def _unique_asset_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in candidates:
        asset_id = str(candidate.get("asset_id") or "")
        if not asset_id or asset_id in seen:
            continue
        seen.add(asset_id)
        selected.append(candidate)
    return selected


def _real_asset_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [candidate for candidate in candidates if _is_real_asset_candidate(candidate)]


def _is_real_asset_candidate(candidate: Mapping[str, Any]) -> bool:
    identity_status = str(candidate.get("identity_status") or "")
    asset_type = str(candidate.get("asset_type") or "")
    asset_id = str(candidate.get("asset_id") or "")
    if identity_status in {"unresolved", "ambiguous"}:
        return False
    if asset_type.startswith(("unresolved", "ambiguous")):
        return False
    return not asset_id.startswith(("asset:unresolved", "asset:ambiguous"))


def _symbol(mention: Mapping[str, Any]) -> str | None:
    value = mention.get("normalized_symbol")
    if value is None:
        return None
    stripped = str(value).strip().lstrip("$")
    if not stripped:
        return None
    return stripped.upper() if stripped.isascii() else stripped


def _event_id(mention: Mapping[str, Any]) -> str:
    return str(mention["event_id"])


def _created_at_ms(mention: Mapping[str, Any]) -> int:
    return int(mention.get("created_at_ms") or mention.get("received_at_ms") or 0)


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
