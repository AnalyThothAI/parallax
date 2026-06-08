from __future__ import annotations

import inspect
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from parallax.domains.asset_market.providers import CexTicker, DexTokenQuote, DexTokenQuoteRequest
from parallax.domains.pulse_lab.providers import DEFAULT_PULSE_AGENT_RUNTIME_CONTRACT, PulseDecisionResult
from parallax.domains.pulse_lab.types.agent_decision import (
    BullBearView,
    FinalDecision,
    StageRunAudit,
    TradePlaybook,
)
from parallax.platform.agent_execution import AgentCapacityReservation


class FakeGmgnUpstreamClient:
    """Deterministically emits captured GMGN frames into the collector boundary."""

    def __init__(
        self,
        frames: Sequence[Any],
        on_frame: Callable[..., Any],
        *,
        received_at_ms: int,
    ) -> None:
        self.frames = list(frames)
        self.on_frame = on_frame
        self.received_at_ms = int(received_at_ms)
        self.closed = False

    async def run(self) -> None:
        for frame in self.frames:
            result = self.on_frame(frame, received_at_ms=self.received_at_ms)
            if inspect.isawaitable(result):
                await result

    async def aclose(self) -> None:
        self.closed = True


class FakeDexQuoteProvider:
    """Current DexTokenQuoteProvider protocol, with deterministic current-fact output."""

    def __init__(
        self,
        *,
        observed_at_ms: int,
        price_usd: float = 0.129,
        market_cap_usd: float = 1_234_567.0,
        liquidity_usd: float = 456_789.0,
        volume_24h_usd: float = 98_765.0,
        holders: int = 4321,
    ) -> None:
        self.observed_at_ms = int(observed_at_ms)
        self.price_usd = price_usd
        self.market_cap_usd = market_cap_usd
        self.liquidity_usd = liquidity_usd
        self.volume_24h_usd = volume_24h_usd
        self.holders = holders
        self.requests: list[list[tuple[str, str]]] = []

    def token_quotes(self, tokens: list[DexTokenQuoteRequest]) -> list[DexTokenQuote]:
        self.requests.append([(token.chain_id, token.address.lower()) for token in tokens])
        return [
            DexTokenQuote(
                chain_id=token.chain_id,
                address=token.address.lower(),
                observed_at_ms=self.observed_at_ms,
                price_usd=self.price_usd,
                market_cap_usd=self.market_cap_usd,
                liquidity_usd=self.liquidity_usd,
                volume_24h_usd=self.volume_24h_usd,
                holders=self.holders,
                raw={
                    "provider": "fake_dex_quote",
                    "chain_id": token.chain_id,
                    "address": token.address.lower(),
                },
            )
            for token in tokens
        ]


class FakeCexQuoteProvider:
    """Minimal CEX provider for hot-path wiring completeness."""

    def __init__(self, tickers: Sequence[CexTicker] = ()) -> None:
        self._tickers = list(tickers)
        self.requests: list[str] = []

    def tickers(self, *, inst_type: str) -> list[CexTicker]:
        self.requests.append(inst_type)
        return [ticker for ticker in self._tickers if ticker.inst_type == inst_type]

    def ticker(self, *, inst_id: str) -> CexTicker | None:
        self.requests.append(inst_id)
        return next((ticker for ticker in self._tickers if ticker.inst_id == inst_id), None)

    def candles(self, *, inst_id: str, bar: str, limit: int) -> list[Any]:
        self.requests.append(f"{inst_id}:{bar}:{limit}")
        return []


class FakePulseDecisionProvider:
    provider = "fake"
    model = "fake-pulse"
    timeout_seconds = 1.0
    artifact_version_hash = "artifact:fake-hot-path"
    runtime_contract = DEFAULT_PULSE_AGENT_RUNTIME_CONTRACT

    def __init__(self) -> None:
        self.contexts: list[dict[str, Any]] = []

    def try_reserve_execution(
        self,
        lane: str,
        *,
        child_lanes: tuple[str, ...] = (),
        rate_units: int = 1,
        scope: str = "execution",
    ) -> AgentCapacityReservation:
        return AgentCapacityReservation(
            lane=lane,
            acquired=True,
            child_lanes=child_lanes,
            rate_units=rate_units,
            scope=scope,
        )

    def model_for_lane(self, lane: str) -> str:
        if lane == "pulse.decision":
            return self.model
        return ""

    def request_audit(
        self,
        *,
        context: dict[str, Any],
        run_id: str,
        job: dict[str, Any],
        route: str,
        completeness: dict[str, Any],
        runtime_manifest: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "backend": "fake",
            "execution_trace_id": f"trace-{run_id}",
            "workflow_name": "pulse-hot-path",
            "agent_name": "pulse-hot-path-agent",
            "prompt_version": "pulse-decision-prompt-v2",
            "schema_version": "pulse-decision-v2",
            "artifact_version_hash": self.artifact_version_hash,
            "runtime_version": runtime_manifest["runtime_version"],
            "runtime_hash": "sha256:hot-path",
            "trace_metadata": {
                "candidate_id": context["candidate_id"],
                "route": route,
                "job_id": job.get("job_id"),
            },
            "input_hash": "input-hot-path",
            "usage": {"input_tokens": 120, "output_tokens": 64},
        }

    async def run_decision_pipeline(
        self,
        *,
        context: dict[str, Any],
        run_id: str,
        job: dict[str, Any],
        route: str,
        completeness: dict[str, Any],
        runtime_manifest: dict[str, Any],
        parent_reservation: AgentCapacityReservation | None = None,
    ) -> PulseDecisionResult:
        self.contexts.append(context)
        evidence_ids = _event_ids(context)
        allowed_refs = [
            str(ref.get("ref_id"))
            for ref in context.get("evidence_packet", {}).get("allowed_evidence_refs", [])
            if isinstance(ref, dict) and ref.get("ref_id")
        ]
        supporting_refs = tuple(ref for ref in allowed_refs if ref.startswith("event:"))[:1] or tuple(allowed_refs[:1])
        risk_refs = tuple(ref for ref in allowed_refs if ref.startswith("market:"))[:1] or supporting_refs
        final = FinalDecision(
            route=route,  # type: ignore[arg-type]
            recommendation="trade_candidate",
            confidence=0.86,
            summary_zh="Deterministic fixture supports a trade-candidate surface.",
            narrative_archetype="social_spread",
            narrative_thesis_zh="Fresh attention and resolved market facts support continued monitoring.",
            bull_view=BullBearView(
                strength="strong",
                thesis_zh="Fresh attention and market data align.",
                supporting_event_ids=evidence_ids,
            ),
            bear_view=BullBearView(
                strength="weak",
                thesis_zh="Single captured event still limits confidence.",
                supporting_event_ids=evidence_ids,
            ),
            playbook=TradePlaybook(
                has_playbook=True,
                watch_signals=["continued mention growth", "liquidity remains healthy"],
                exit_triggers=["attention fades", "liquidity degrades"],
                monitoring_horizon="4h",
            ),
            evidence_event_urls={event_id: f"https://x.com/fixture/status/{event_id}" for event_id in evidence_ids},
            invalidation_conditions=["No follow-through in the next window."],
            residual_risks=["Fixture path uses deterministic providers."],
            evidence_event_ids=evidence_ids,
            supporting_evidence_refs=supporting_refs,
            risk_evidence_refs=risk_refs,
        )
        audit = self.request_audit(
            context=context,
            run_id=run_id,
            job=job,
            route=route,
            completeness=completeness,
            runtime_manifest=runtime_manifest,
        )
        return PulseDecisionResult(
            final_decision=final,
            agent_run_audit={**audit, "output_hash": "output-hot-path"},
            stage_audits=(
                StageRunAudit(
                    stage="pulse_decision",
                    route=route,  # type: ignore[arg-type]
                    attempt_index=0,
                    input_json={"context": context, "completeness": completeness},
                    prompt_text="pulse decision prompt",
                    response_json=final.model_dump(mode="json"),
                    trace_metadata_json={},
                    usage_json={"input_tokens": 120, "output_tokens": 42},
                    latency_ms=17,
                    status="ok",
                ),
            ),
        )


@dataclass
class RecordingNotificationProvider:
    deliveries: list[dict[str, Any]] = field(default_factory=list)

    def notify(self, *, url: str, title: str, body: str, body_format: str = "text") -> None:
        self.deliveries.append({"url": url, "title": title, "body": body, "body_format": body_format})

    def notify_markdown(self, *, url: str, title: str, body: str) -> None:
        self.deliveries.append({"url": url, "title": title, "body": body, "body_format": "markdown"})


class RecordingWakeEmitter:
    def __init__(self) -> None:
        self.market_tick_writes: list[tuple[str, str]] = []

    def notify_market_tick_written(self, *, target_type: str, target_id: str) -> None:
        self.market_tick_writes.append((target_type, target_id))


def _event_ids(context: dict[str, Any]) -> list[str]:
    raw = context.get("evidence_event_ids") or context.get("source_event_ids") or ["event-hot-path"]
    return [str(item) for item in raw if str(item).strip()] or ["event-hot-path"]
