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
        self.concurrency = max(1, int(getattr(resolved_settings, "concurrency", 4) or 4))
        self.clock = clock or _now_ms
        self._recent_tier2_attempts: set[tuple[str, str]] = set()

    async def run_once(self) -> WorkerResult:
        # DB read happens off the event loop; provider IO must not run while a
        # DB session is held, so we materialize rows first, then drop the session.
        rows = await asyncio.to_thread(self._list_tier2_rows)
        targets = _poll_targets(rows)

        # New semaphore per cycle so concurrency state does not leak across runs.
        semaphore = asyncio.Semaphore(self.concurrency)
        chain_result, cex_result = await asyncio.gather(
            self._poll_chain_targets_async(targets.chain_targets, semaphore),
            self._poll_cex_targets_async(targets.cex_targets, semaphore),
        )

        skipped_reasons: Counter[str] = Counter(targets.skipped_reasons)
        skipped_reasons.update(chain_result.skipped_reasons)
        skipped_reasons.update(cex_result.skipped_reasons)
        ticks = [*chain_result.ticks, *cex_result.ticks]

        inserted = await asyncio.to_thread(self._persist_ticks, ticks)
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
        exclude_keys = _target_key_dicts(self._recent_tier2_attempts)
        with self.db.worker_session(self.name) as repos:
            rows = _list_tier2_page(
                repos,
                limit=self.batch_size,
                exclude_keys=exclude_keys,
            )
            if not rows and exclude_keys:
                self._recent_tier2_attempts.clear()
                rows = repos.token_capture_tiers.list_by_tier(2, limit=self.batch_size)
        self._remember_tier2_attempts(rows)
        return [dict(row) for row in rows]

    def _remember_tier2_attempts(self, rows: Sequence[Mapping[str, Any]]) -> None:
        for row in rows:
            target_type = str(row.get("target_type") or "").strip()
            target_id = str(row.get("target_id") or "").strip()
            if target_type and target_id:
                self._recent_tier2_attempts.add((target_type, target_id))
        max_recent = max(self.batch_size * 50, 1_000)
        if len(self._recent_tier2_attempts) > max_recent:
            self._recent_tier2_attempts.clear()

    async def _poll_chain_targets_async(
        self,
        targets: list[_ChainTarget],
        semaphore: asyncio.Semaphore,
    ) -> _PollProviderResult:
        provider = getattr(self.providers, "dex_quote_market", None)
        if provider is None:
            skipped: Counter[str] = Counter()
            skipped["dex_provider_unavailable"] += len(targets)
            return _PollProviderResult(ticks=[], skipped_reasons=skipped)
        if not targets:
            return _PollProviderResult(ticks=[], skipped_reasons=Counter())

        requests = [DexTokenQuoteRequest(chain_id=target.chain_id, address=target.address) for target in targets]
        try:
            quotes = await asyncio.to_thread(provider.token_quotes, requests)
        except Exception as exc:
            self.logger.bind(reason=_provider_error_reason(exc), target_count=len(targets)).warning(
                "market tick poll batch quote failed; retrying individually"
            )
            return await self._poll_chain_targets_individually_async(provider, targets, semaphore)

        skipped_reasons: Counter[str] = Counter()
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
        return _PollProviderResult(ticks=ticks, skipped_reasons=skipped_reasons)

    async def _poll_chain_targets_individually_async(
        self,
        provider: Any,
        targets: list[_ChainTarget],
        semaphore: asyncio.Semaphore,
    ) -> _PollProviderResult:
        async def _one(target: _ChainTarget) -> _SingleTargetOutcome:
            async with semaphore:
                try:
                    quotes = await asyncio.to_thread(
                        provider.token_quotes,
                        [DexTokenQuoteRequest(chain_id=target.chain_id, address=target.address)],
                    )
                except Exception as exc:
                    return _SingleTargetOutcome(tick=None, skip_reason=_provider_error_reason(exc))
            quote = _quote_for_chain_target(quotes, target=target)
            if quote is None:
                return _SingleTargetOutcome(tick=None, skip_reason="dex_quote_unavailable")
            tick = _tick_from_dex_quote(quote, target=target, received_at_ms=int(self.clock()))
            if tick is None:
                return _SingleTargetOutcome(tick=None, skip_reason="invalid_price")
            return _SingleTargetOutcome(tick=tick, skip_reason=None)

        outcomes = await asyncio.gather(*[_one(target) for target in targets])
        return self._collect_outcomes(targets_kind="chain_token", targets=targets, outcomes=outcomes)

    async def _poll_cex_targets_async(
        self,
        targets: list[_CexTarget],
        semaphore: asyncio.Semaphore,
    ) -> _PollProviderResult:
        provider = getattr(self.providers, "message_cex_market", None)
        if provider is None:
            skipped: Counter[str] = Counter()
            skipped["cex_provider_unavailable"] += len(targets)
            return _PollProviderResult(ticks=[], skipped_reasons=skipped)
        if not targets:
            return _PollProviderResult(ticks=[], skipped_reasons=Counter())

        async def _one(target: _CexTarget) -> _SingleTargetOutcome:
            async with semaphore:
                try:
                    ticker = await asyncio.to_thread(provider.ticker, inst_id=target.instrument)
                except Exception as exc:
                    return _SingleTargetOutcome(tick=None, skip_reason=_provider_error_reason(exc))
            if ticker is None:
                return _SingleTargetOutcome(tick=None, skip_reason="cex_quote_unavailable")
            tick = _tick_from_cex_ticker(ticker, target=target, received_at_ms=int(self.clock()))
            if tick is None:
                return _SingleTargetOutcome(tick=None, skip_reason="invalid_price")
            return _SingleTargetOutcome(tick=tick, skip_reason=None)

        outcomes = await asyncio.gather(*[_one(target) for target in targets])
        return self._collect_outcomes(targets_kind="cex_symbol", targets=targets, outcomes=outcomes)

    def _collect_outcomes(
        self,
        *,
        targets_kind: str,
        targets: Sequence[Any],
        outcomes: Sequence[_SingleTargetOutcome],
    ) -> _PollProviderResult:
        skipped_reasons: Counter[str] = Counter()
        ticks: list[MarketTick] = []
        for target, outcome in zip(targets, outcomes, strict=True):
            if outcome.tick is not None:
                ticks.append(outcome.tick)
                continue
            reason = outcome.skip_reason or "provider_error"
            skipped_reasons[reason] += 1
            self.logger.bind(
                target_type=targets_kind,
                target_id=target.target_id,
                reason=reason,
            ).warning("market tick poll quote skipped")
        return _PollProviderResult(ticks=ticks, skipped_reasons=skipped_reasons)

    def _persist_ticks(self, ticks: Iterable[MarketTick]) -> int:
        materialized = list(ticks)
        if not materialized:
            return 0
        by_tick_id = {tick.tick_id: tick for tick in materialized}
        with self.db.worker_session(self.name) as repos:
            inserted_ids = list(repos.market_ticks.insert_ticks_returning_ids(materialized))
            _commit_if_supported(repos)
        changed_targets = list(
            dict.fromkeys(
                (tick.target_type, tick.target_id)
                for tick_id in inserted_ids
                if (tick := by_tick_id.get(str(tick_id))) is not None
            )
        )
        for target_type, target_id in changed_targets:
            _emit_wake(self.wake_emitter, target_type=target_type, target_id=target_id)
        return len(inserted_ids)


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


@dataclass(frozen=True, slots=True)
class _PollProviderResult:
    ticks: list[MarketTick]
    skipped_reasons: Counter[str]


@dataclass(frozen=True, slots=True)
class _SingleTargetOutcome:
    tick: MarketTick | None
    skip_reason: str | None


def _list_tier2_page(
    repos: Any,
    *,
    limit: int,
    exclude_keys: list[dict[str, str]],
) -> list[Mapping[str, Any]]:
    if exclude_keys:
        rows = repos.token_capture_tiers.list_by_tier(2, limit=limit, exclude_keys=exclude_keys)
    else:
        rows = repos.token_capture_tiers.list_by_tier(2, limit=limit)
    return [dict(row) for row in rows]


def _target_key_dicts(keys: set[tuple[str, str]]) -> list[dict[str, str]]:
    return [{"target_type": target_type, "target_id": target_id} for target_type, target_id in sorted(keys)]


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
            soft_timeout_seconds=120.0,
            hard_timeout_seconds=180.0,
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
