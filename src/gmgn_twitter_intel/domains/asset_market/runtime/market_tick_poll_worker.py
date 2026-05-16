from __future__ import annotations

import asyncio
import time
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from types import SimpleNamespace
from typing import Any

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_result import WorkerResult
from gmgn_twitter_intel.domains.asset_market.providers import CexTicker, DexTokenQuote, DexTokenQuoteRequest
from gmgn_twitter_intel.domains.asset_market.types import (
    DEX_QUOTE_SOURCE_PROVIDERS,
    MarketTick,
    MarketTickSourceProvider,
    MarketTickSourceTier,
    market_tick_id,
)

SOURCE_TIER: MarketTickSourceTier = "tier2_poll"
DEX_SOURCE_PROVIDER: MarketTickSourceProvider = "okx_dex_rest"
CEX_SOURCE_PROVIDER: MarketTickSourceProvider = "okx_cex_rest"
DEFAULT_BATCH_SIZE = 100


class MarketTickPollWorker(WorkerBase):
    worker_name = "market_tick_poll"

    def __init__(
        self,
        *,
        pool_bundle: Any | None = None,
        providers: Any | None = None,
        dex_quote_market: Any | None = None,
        message_cex_market: Any | None = None,
        wake_emitter: Any | None = None,
        wake_bus: Any | None = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
        interval_seconds: float | None = None,
        clock: Any | None = None,
        name: str = "market_tick_poll",
        settings: Any | None = None,
        db: Any | None = None,
        telemetry: Any | None = None,
    ) -> None:
        resolved_settings = _settings(settings, interval_seconds=interval_seconds, batch_size=batch_size)
        super().__init__(
            name=name,
            settings=resolved_settings,
            db=pool_bundle or db,
            telemetry=telemetry or object(),
        )
        self.providers = providers or SimpleNamespace(
            dex_quote_market=dex_quote_market,
            message_cex_market=message_cex_market,
        )
        self.wake_emitter = wake_emitter or wake_bus
        self.batch_size = max(1, int(getattr(resolved_settings, "batch_size", batch_size)))
        self.clock = clock or _now_ms

    async def run_once(self) -> WorkerResult:
        return await asyncio.to_thread(self._run_once_sync)

    def _run_once_sync(self) -> WorkerResult:
        rows = self._list_tier2_rows()
        targets = _poll_targets(rows)

        ticks: list[MarketTick] = []
        skipped_reasons = Counter(targets.skipped_reasons)
        ticks.extend(self._poll_chain_targets(targets.chain_targets, skipped_reasons))
        ticks.extend(self._poll_cex_targets(targets.cex_targets, skipped_reasons))

        inserted = self._persist_ticks(ticks)
        return WorkerResult(
            processed=inserted,
            skipped=sum(skipped_reasons.values()),
            notes={
                "targets_selected": len(rows),
                "chain_targets": len(targets.chain_targets),
                "cex_targets": len(targets.cex_targets),
                "ticks_attempted": len(ticks),
                "ticks_inserted": inserted,
                "skipped_reasons": dict(sorted(skipped_reasons.items())),
            },
        )

    def _list_tier2_rows(self) -> list[dict[str, Any]]:
        with self.db.worker_session(self.name) as repos:
            rows = repos.token_capture_tiers.list_by_tier(2, limit=self.batch_size)
        return [dict(row) for row in rows]

    def _poll_chain_targets(self, targets: list[_ChainTarget], skipped_reasons: Counter[str]) -> list[MarketTick]:
        provider = getattr(self.providers, "dex_quote_market", None)
        if provider is None:
            skipped_reasons["dex_provider_unavailable"] += len(targets)
            return []

        requests = [DexTokenQuoteRequest(chain_id=target.chain_id, address=target.address) for target in targets]
        try:
            quotes = provider.token_quotes(requests)
        except Exception as exc:
            self.logger.bind(reason=_provider_error_reason(exc), target_count=len(targets)).warning(
                "market tick poll batch quote failed; retrying individually"
            )
            return self._poll_chain_targets_individually(provider, targets, skipped_reasons)

        quotes_by_key = {_target_key(quote.chain_id, quote.address): quote for quote in quotes}
        ticks: list[MarketTick] = []
        for target in targets:
            quote = quotes_by_key.get(_target_key(target.chain_id, target.address))
            if quote is None:
                skipped_reasons["dex_quote_unavailable"] += 1
                self.logger.bind(
                    target_type="chain_token",
                    target_id=target.target_id,
                    reason="dex_quote_unavailable",
                ).warning("market tick poll quote skipped")
                continue
            tick = _tick_from_dex_quote(quote, target=target, received_at_ms=int(self.clock()))
            if tick is None:
                skipped_reasons["invalid_price"] += 1
                self.logger.bind(
                    target_type="chain_token",
                    target_id=target.target_id,
                    reason="invalid_price",
                ).warning("market tick poll quote skipped")
                continue
            ticks.append(tick)
        return ticks

    def _poll_chain_targets_individually(
        self,
        provider: Any,
        targets: list[_ChainTarget],
        skipped_reasons: Counter[str],
    ) -> list[MarketTick]:
        ticks: list[MarketTick] = []
        for target in targets:
            try:
                quotes = provider.token_quotes([DexTokenQuoteRequest(chain_id=target.chain_id, address=target.address)])
            except Exception as exc:
                reason = _provider_error_reason(exc)
                skipped_reasons[reason] += 1
                self.logger.bind(
                    target_type="chain_token",
                    target_id=target.target_id,
                    reason=reason,
                ).warning("market tick poll quote skipped")
                continue
            quote = _quote_for_chain_target(quotes, target=target)
            if quote is None:
                skipped_reasons["dex_quote_unavailable"] += 1
                self.logger.bind(
                    target_type="chain_token",
                    target_id=target.target_id,
                    reason="dex_quote_unavailable",
                ).warning("market tick poll quote skipped")
                continue
            tick = _tick_from_dex_quote(quote, target=target, received_at_ms=int(self.clock()))
            if tick is None:
                skipped_reasons["invalid_price"] += 1
                self.logger.bind(
                    target_type="chain_token",
                    target_id=target.target_id,
                    reason="invalid_price",
                ).warning("market tick poll quote skipped")
                continue
            ticks.append(tick)
        return ticks

    def _poll_cex_targets(self, targets: list[_CexTarget], skipped_reasons: Counter[str]) -> list[MarketTick]:
        provider = getattr(self.providers, "message_cex_market", None)
        if provider is None:
            skipped_reasons["cex_provider_unavailable"] += len(targets)
            return []

        ticks: list[MarketTick] = []
        for target in targets:
            try:
                ticker = provider.ticker(inst_id=target.instrument)
            except Exception as exc:
                reason = _provider_error_reason(exc)
                skipped_reasons[reason] += 1
                self.logger.bind(
                    target_type="cex_symbol",
                    target_id=target.target_id,
                    reason=reason,
                ).warning("market tick poll quote skipped")
                continue
            if ticker is None:
                skipped_reasons["cex_quote_unavailable"] += 1
                self.logger.bind(
                    target_type="cex_symbol",
                    target_id=target.target_id,
                    reason="cex_quote_unavailable",
                ).warning("market tick poll quote skipped")
                continue
            tick = _tick_from_cex_ticker(ticker, target=target, received_at_ms=int(self.clock()))
            if tick is None:
                skipped_reasons["invalid_price"] += 1
                self.logger.bind(
                    target_type="cex_symbol",
                    target_id=target.target_id,
                    reason="invalid_price",
                ).warning("market tick poll quote skipped")
                continue
            ticks.append(tick)
        return ticks

    def _persist_ticks(self, ticks: Iterable[MarketTick]) -> int:
        materialized = list(ticks)
        if not materialized:
            return 0
        with self.db.worker_session(self.name) as repos:
            inserted = int(repos.market_ticks.insert_ticks(materialized))
            _commit_if_supported(repos)
        for tick in materialized:
            _emit_wake(self.wake_emitter, target_type=tick.target_type, target_id=tick.target_id)
        return inserted


@dataclass(frozen=True, slots=True)
class _ChainTarget:
    target_id: str
    chain_id: str
    address: str


@dataclass(frozen=True, slots=True)
class _CexTarget:
    target_id: str
    exchange: str
    instrument: str


@dataclass(frozen=True, slots=True)
class _PollTargets:
    chain_targets: list[_ChainTarget]
    cex_targets: list[_CexTarget]
    skipped_reasons: Counter[str]


def _poll_targets(rows: Sequence[Mapping[str, Any]]) -> _PollTargets:
    chain_targets: list[_ChainTarget] = []
    cex_targets: list[_CexTarget] = []
    skipped_reasons: Counter[str] = Counter()

    for row in rows:
        target_type = _clean_str(row.get("target_type"))
        target_id = _clean_str(row.get("target_id"))
        if target_type == "chain_token":
            chain_target = _chain_target(target_id)
            if chain_target is None:
                skipped_reasons["invalid_chain_target"] += 1
                continue
            chain_targets.append(chain_target)
            continue
        if target_type == "cex_symbol":
            cex_target = _cex_target(target_id)
            if cex_target is None:
                skipped_reasons["invalid_cex_target"] += 1
                continue
            cex_targets.append(cex_target)
            continue
        skipped_reasons["unsupported_target_type"] += 1

    return _PollTargets(
        chain_targets=chain_targets,
        cex_targets=cex_targets,
        skipped_reasons=skipped_reasons,
    )


def _chain_target(target_id: str) -> _ChainTarget | None:
    chain_id, separator, address = target_id.rpartition(":")
    if not separator:
        return None
    chain_id = chain_id.strip()
    address = address.strip()
    if not chain_id or not address:
        return None
    return _ChainTarget(target_id=target_id, chain_id=chain_id, address=address)


def _cex_target(target_id: str) -> _CexTarget | None:
    exchange, separator, instrument = target_id.partition(":")
    if not separator:
        return None
    exchange = exchange.strip()
    instrument = instrument.strip()
    if not exchange or not instrument or ":" in instrument:
        return None
    return _CexTarget(target_id=target_id, exchange=exchange, instrument=instrument)


def _quote_for_chain_target(quotes: list[DexTokenQuote], *, target: _ChainTarget) -> DexTokenQuote | None:
    target_key = _target_key(target.chain_id, target.address)
    for quote in quotes:
        if _target_key(quote.chain_id, quote.address) == target_key:
            return quote
    return None


def _tick_from_dex_quote(
    quote: DexTokenQuote,
    *,
    target: _ChainTarget,
    received_at_ms: int,
) -> MarketTick | None:
    price_usd = _positive_decimal(quote.price_usd)
    if price_usd is None:
        return None
    observed_at_ms = int(quote.observed_at_ms or received_at_ms)
    source_provider = _dex_source_provider(quote)
    return MarketTick(
        tick_id=market_tick_id(
            target_type="chain_token",
            target_id=target.target_id,
            source_provider=source_provider,
            observed_at_ms=observed_at_ms,
        ),
        target_type="chain_token",
        target_id=target.target_id,
        chain=target.chain_id,
        token_address=target.address,
        exchange=None,
        instrument=None,
        pricefeed_id=None,
        source_tier=SOURCE_TIER,
        source_provider=source_provider,
        observed_at_ms=observed_at_ms,
        received_at_ms=received_at_ms,
        price_usd=price_usd,
        liquidity_usd=_optional_decimal(quote.liquidity_usd),
        volume_24h_usd=_optional_decimal(quote.volume_24h_usd),
        market_cap_usd=_optional_decimal(quote.market_cap_usd),
        holders=_int_or_none(quote.holders),
        created_at_ms=received_at_ms,
        raw_payload_json=dict(quote.raw),
    )


def _tick_from_cex_ticker(
    ticker: CexTicker,
    *,
    target: _CexTarget,
    received_at_ms: int,
) -> MarketTick | None:
    price_usd = _positive_decimal(ticker.last_price)
    if price_usd is None:
        return None
    observed_at_ms = _ticker_observed_at_ms(ticker) or received_at_ms
    return MarketTick(
        tick_id=market_tick_id(
            target_type="cex_symbol",
            target_id=target.target_id,
            source_provider=CEX_SOURCE_PROVIDER,
            observed_at_ms=observed_at_ms,
        ),
        target_type="cex_symbol",
        target_id=target.target_id,
        chain=None,
        token_address=None,
        exchange=target.exchange,
        instrument=target.instrument,
        pricefeed_id=None,
        source_tier=SOURCE_TIER,
        source_provider=CEX_SOURCE_PROVIDER,
        observed_at_ms=observed_at_ms,
        received_at_ms=received_at_ms,
        price_usd=price_usd,
        liquidity_usd=None,
        volume_24h_usd=_optional_decimal(ticker.volume_24h),
        market_cap_usd=None,
        holders=None,
        created_at_ms=received_at_ms,
        raw_payload_json=dict(ticker.raw),
    )


def _ticker_observed_at_ms(ticker: CexTicker) -> int | None:
    for key in ("observed_at_ms", "ts", "timestamp", "time"):
        observed_at_ms = _int_or_none(ticker.raw.get(key))
        if observed_at_ms is not None:
            return observed_at_ms
    return None


def _positive_decimal(value: Any) -> Decimal | None:
    result = _optional_decimal(value)
    if result is None or result <= 0:
        return None
    return result


def _optional_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not result.is_finite():
        return None
    return result


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _clean_str(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _target_key(chain_id: str, address: str) -> tuple[str, str]:
    return (str(chain_id).strip(), str(address).strip().lower())


def _dex_source_provider(quote: DexTokenQuote) -> MarketTickSourceProvider:
    source_provider = _clean_str(quote.raw.get("source_provider"))
    if source_provider in DEX_QUOTE_SOURCE_PROVIDERS:
        return source_provider
    return DEX_SOURCE_PROVIDER


def _emit_wake(wake_emitter: Any, *, target_type: str, target_id: str) -> None:
    if wake_emitter is None:
        return
    wake_emitter.notify_market_tick_written(target_type=target_type, target_id=target_id)


def _commit_if_supported(repos: Any) -> None:
    conn = getattr(repos, "conn", None)
    commit = getattr(conn, "commit", None)
    if callable(commit):
        commit()
        return
    commit = getattr(repos, "commit", None)
    if callable(commit):
        commit()


def _provider_error_reason(exc: Exception) -> str:
    if isinstance(exc, TimeoutError):
        return "provider_timeout"
    text = f"{type(exc).__name__} {exc}".lower()
    if "429" in text or ("rate" in text and "limit" in text):
        return "rate_limited"
    if "timeout" in text or "timed out" in text:
        return "provider_timeout"
    return "provider_error"


def _settings(settings: Any | None, *, interval_seconds: float | None, batch_size: int) -> Any:
    if settings is None:
        return SimpleNamespace(
            enabled=True,
            interval_seconds=interval_seconds if interval_seconds is not None else 5.0,
            timeout_seconds=120.0,
            batch_size=batch_size,
        )
    if interval_seconds is None:
        return settings
    try:
        settings.interval_seconds = interval_seconds
        return settings
    except Exception:
        values = dict(getattr(settings, "__dict__", {}))
        values["interval_seconds"] = interval_seconds
        return SimpleNamespace(**values)


def _now_ms() -> int:
    return int(time.time() * 1000)


__all__ = ["MarketTickPollWorker"]
