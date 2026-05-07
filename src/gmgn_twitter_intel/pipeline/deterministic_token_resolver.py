from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

RESOLVER_POLICY_VERSION = "token_radar_v4_deterministic_resolver"
FRESH_OBSERVATION_MS = 5 * 60 * 1000
DOMINANCE_GAP = Decimal("1.0")
MIN_DOMINANT_MARKET_CAP_USD = Decimal("250000")
MIN_DOMINANT_HOLDERS = Decimal("1000")
MIN_DOMINANT_LIQUIDITY_USD = Decimal("100000")


@dataclass(frozen=True, slots=True)
class MentionKeys:
    symbol: str | None = None
    chain_id: str | None = None
    address: str | None = None
    cex_pricefeed_id: str | None = None
    exchange: str | None = None
    dex_token_provider: str | None = None


@dataclass(frozen=True, slots=True)
class DeterministicResolution:
    intent_id: str
    event_id: str
    resolution_status: str
    target_type: str | None
    target_id: str | None
    pricefeed_id: str | None
    resolver_policy_version: str
    reason_codes: list[str]
    candidate_ids: list[str]
    lookup_keys: list[str]
    decision_time_ms: int
    created_at_ms: int


class DeterministicTokenResolver:
    def __init__(self, *, registry: Any):
        self.registry = registry

    def resolve(
        self,
        *,
        intent_id: str,
        event_id: str,
        keys: MentionKeys,
        decision_time_ms: int,
    ) -> DeterministicResolution:
        lookup_keys = _lookup_keys(keys)
        if keys.cex_pricefeed_id and keys.exchange:
            return self._resolve_cex_pricefeed(
                intent_id=intent_id,
                event_id=event_id,
                keys=keys,
                lookup_keys=lookup_keys,
                decision_time_ms=decision_time_ms,
            )
        if keys.address and keys.chain_id:
            return self._resolve_chain_address(
                intent_id=intent_id,
                event_id=event_id,
                keys=keys,
                lookup_keys=lookup_keys,
                decision_time_ms=decision_time_ms,
            )
        if keys.address:
            return self._resolve_address_without_chain(
                intent_id=intent_id,
                event_id=event_id,
                keys=keys,
                lookup_keys=lookup_keys,
                decision_time_ms=decision_time_ms,
            )
        if keys.symbol:
            return self._resolve_symbol(
                intent_id=intent_id,
                event_id=event_id,
                keys=keys,
                lookup_keys=lookup_keys,
                decision_time_ms=decision_time_ms,
            )
        return _resolution(
            intent_id=intent_id,
            event_id=event_id,
            status="NIL",
            target_type=None,
            target_id=None,
            reason_codes=["NO_RESOLVABLE_MENTION"],
            lookup_keys=lookup_keys,
            decision_time_ms=decision_time_ms,
        )

    def _resolve_cex_pricefeed(
        self,
        *,
        intent_id: str,
        event_id: str,
        keys: MentionKeys,
        lookup_keys: list[str],
        decision_time_ms: int,
    ) -> DeterministicResolution:
        row = self.registry.find_cex_pricefeed(
            exchange=str(keys.exchange),
            native_market_id=str(keys.cex_pricefeed_id),
        )
        if row:
            target_type = str(row["subject_type"])
            target_id = str(row["subject_id"])
            pricefeed_id = str(row["pricefeed_id"])
            return _resolution(
                intent_id=intent_id,
                event_id=event_id,
                status="EXACT",
                target_type=target_type,
                target_id=target_id,
                pricefeed_id=pricefeed_id,
                reason_codes=["CEX_NATIVE_PRICEFEED_EXACT"],
                lookup_keys=lookup_keys,
                candidate_ids=[pricefeed_id, target_id],
                decision_time_ms=decision_time_ms,
            )
        return _resolution(
            intent_id=intent_id,
            event_id=event_id,
            status="NIL",
            target_type=None,
            target_id=None,
            reason_codes=["CEX_PRICEFEED_NOT_IN_REGISTRY"],
            lookup_keys=lookup_keys,
            decision_time_ms=decision_time_ms,
        )

    def _resolve_chain_address(
        self,
        *,
        intent_id: str,
        event_id: str,
        keys: MentionKeys,
        lookup_keys: list[str],
        decision_time_ms: int,
    ) -> DeterministicResolution:
        rows = self.registry.find_assets_by_address(chain_id=keys.chain_id, address=keys.address)
        if len(rows) == 1:
            return _resolution(
                intent_id=intent_id,
                event_id=event_id,
                status="EXACT",
                target_type="Asset",
                target_id=str(rows[0]["asset_id"]),
                reason_codes=["CHAIN_ADDRESS_EXACT"],
                lookup_keys=lookup_keys,
                candidate_ids=[str(rows[0]["asset_id"])],
                decision_time_ms=decision_time_ms,
            )
        return _resolution(
            intent_id=intent_id,
            event_id=event_id,
            status="NIL",
            target_type=None,
            target_id=None,
            reason_codes=["ADDRESS_NOT_IN_REGISTRY"],
            lookup_keys=lookup_keys,
            decision_time_ms=decision_time_ms,
        )

    def _resolve_address_without_chain(
        self,
        *,
        intent_id: str,
        event_id: str,
        keys: MentionKeys,
        lookup_keys: list[str],
        decision_time_ms: int,
    ) -> DeterministicResolution:
        rows = self.registry.find_assets_by_address(chain_id=None, address=keys.address)
        candidate_ids = [str(row["asset_id"]) for row in rows if row.get("asset_id")]
        if len(candidate_ids) == 1:
            return _resolution(
                intent_id=intent_id,
                event_id=event_id,
                status="UNIQUE_BY_CONTEXT",
                target_type="Asset",
                target_id=candidate_ids[0],
                reason_codes=["ADDRESS_UNIQUE_ACROSS_TRACKED_CHAINS"],
                lookup_keys=lookup_keys,
                candidate_ids=candidate_ids,
                decision_time_ms=decision_time_ms,
            )
        if candidate_ids:
            return _resolution(
                intent_id=intent_id,
                event_id=event_id,
                status="AMBIGUOUS",
                target_type=None,
                target_id=None,
                reason_codes=["ADDRESS_EXISTS_ON_MULTIPLE_CHAINS"],
                lookup_keys=lookup_keys,
                candidate_ids=candidate_ids,
                decision_time_ms=decision_time_ms,
            )
        return _resolution(
            intent_id=intent_id,
            event_id=event_id,
            status="NIL",
            target_type=None,
            target_id=None,
            reason_codes=["ADDRESS_NOT_IN_REGISTRY"],
            lookup_keys=lookup_keys,
            decision_time_ms=decision_time_ms,
        )

    def _resolve_symbol(
        self,
        *,
        intent_id: str,
        event_id: str,
        keys: MentionKeys,
        lookup_keys: list[str],
        decision_time_ms: int,
    ) -> DeterministicResolution:
        symbol = _normalize_symbol(keys.symbol)
        cex_token = self.registry.find_cex_token(symbol)
        if cex_token:
            target_id = str(cex_token["cex_token_id"])
            pricefeed = self.registry.find_preferred_cex_pricefeed(symbol)
            pricefeed_id = str(pricefeed["pricefeed_id"]) if pricefeed else None
            candidate_ids = [target_id]
            if pricefeed_id:
                candidate_ids.insert(0, pricefeed_id)
            return _resolution(
                intent_id=intent_id,
                event_id=event_id,
                status="UNIQUE_BY_CONTEXT",
                target_type="CexToken",
                target_id=target_id,
                pricefeed_id=pricefeed_id,
                reason_codes=["CONFIRMED_CEX_TOKEN"],
                lookup_keys=lookup_keys,
                candidate_ids=candidate_ids,
                decision_time_ms=decision_time_ms,
            )
        assets = self.registry.find_assets_by_symbol_with_latest_observation(symbol)
        active_assets = [
            row
            for row in assets
            if _fresh(row.get("observed_at_ms"), decision_time_ms) and str(row.get("asset_id") or "")
        ]
        candidate_ids = [str(row["asset_id"]) for row in active_assets]
        if len(active_assets) == 1:
            return _resolution(
                intent_id=intent_id,
                event_id=event_id,
                status="UNIQUE_BY_CONTEXT",
                target_type="Asset",
                target_id=str(active_assets[0]["asset_id"]),
                reason_codes=["SINGLE_ACTIVE_CHAIN_ASSET"],
                lookup_keys=lookup_keys,
                candidate_ids=candidate_ids,
                decision_time_ms=decision_time_ms,
            )
        dominant = _market_dominant_asset(active_assets)
        if dominant is not None:
            return _resolution(
                intent_id=intent_id,
                event_id=event_id,
                status="UNIQUE_BY_CONTEXT",
                target_type="Asset",
                target_id=str(dominant["asset_id"]),
                reason_codes=["MARKET_DOMINANT_CHAIN_ASSET"],
                lookup_keys=lookup_keys,
                candidate_ids=candidate_ids,
                decision_time_ms=decision_time_ms,
            )
        if candidate_ids:
            return _resolution(
                intent_id=intent_id,
                event_id=event_id,
                status="AMBIGUOUS",
                target_type=None,
                target_id=None,
                reason_codes=["NO_MARKET_DOMINANT_CHAIN_ASSET"],
                lookup_keys=lookup_keys,
                candidate_ids=candidate_ids,
                decision_time_ms=decision_time_ms,
            )
        return _resolution(
            intent_id=intent_id,
            event_id=event_id,
            status="NIL",
            target_type=None,
            target_id=None,
            reason_codes=["SYMBOL_NOT_IN_REGISTRY"],
            lookup_keys=lookup_keys,
            decision_time_ms=decision_time_ms,
        )


def _market_dominant_asset(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    eligible = [row for row in rows if _dominance_eligible(row)]
    if not eligible:
        return None
    ranked = sorted(eligible, key=_dominance_score, reverse=True)
    top = ranked[0]
    second_score = _dominance_score(ranked[1]) if len(ranked) > 1 else Decimal("-999")
    if _dominance_score(top) - second_score < DOMINANCE_GAP:
        return None
    if (
        _decimal(top.get("market_cap_usd")) < MIN_DOMINANT_MARKET_CAP_USD
        and _decimal(top.get("holders")) < MIN_DOMINANT_HOLDERS
        and _decimal(top.get("liquidity_usd")) < MIN_DOMINANT_LIQUIDITY_USD
    ):
        return None
    return top


def _dominance_eligible(row: dict[str, Any]) -> bool:
    present = sum(
        1
        for key in ("market_cap_usd", "holders", "liquidity_usd")
        if row.get(key) is not None and _decimal(row.get(key)) > 0
    )
    return present >= 2


def _dominance_score(row: dict[str, Any]) -> Decimal:
    return (
        Decimal("0.55") * _log10(_decimal(row.get("market_cap_usd")) + 1)
        + Decimal("0.30") * _log10(_decimal(row.get("holders")) + 1)
        + Decimal("0.15") * _log10(_decimal(row.get("liquidity_usd")) + 1)
    )


def _log10(value: Decimal) -> Decimal:
    if value <= 0:
        return Decimal("0")
    return value.log10()


def _decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _fresh(observed_at_ms: Any, decision_time_ms: int) -> bool:
    if observed_at_ms is None:
        return False
    return max(0, int(decision_time_ms) - int(observed_at_ms)) <= FRESH_OBSERVATION_MS


def _lookup_keys(keys: MentionKeys) -> list[str]:
    out: list[str] = []
    if keys.symbol:
        symbol = _normalize_symbol(keys.symbol)
        out.extend([f"symbol:{symbol}", f"project_symbol:{symbol}", f"cex_token:{symbol}"])
    if keys.address:
        chain = keys.chain_id or "unknown"
        out.append(f"address:{chain}:{str(keys.address).lower()}")
    if keys.cex_pricefeed_id:
        exchange = keys.exchange or "unknown"
        out.append(f"cex_pricefeed:{exchange}:{keys.cex_pricefeed_id}")
    return out


def _resolution(
    *,
    intent_id: str,
    event_id: str,
    status: str,
    target_type: str | None,
    target_id: str | None,
    reason_codes: list[str],
    lookup_keys: list[str],
    decision_time_ms: int,
    candidate_ids: list[str] | None = None,
    pricefeed_id: str | None = None,
) -> DeterministicResolution:
    return DeterministicResolution(
        intent_id=intent_id,
        event_id=event_id,
        resolution_status=status,
        target_type=target_type,
        target_id=target_id,
        pricefeed_id=pricefeed_id,
        resolver_policy_version=RESOLVER_POLICY_VERSION,
        reason_codes=reason_codes,
        candidate_ids=candidate_ids or [],
        lookup_keys=lookup_keys,
        decision_time_ms=int(decision_time_ms),
        created_at_ms=int(decision_time_ms),
    )


def _normalize_symbol(symbol: str | None) -> str:
    return str(symbol or "").strip().lstrip("$").upper()
