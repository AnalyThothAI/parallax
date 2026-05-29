from __future__ import annotations

from typing import Any

from gmgn_twitter_intel.domains.watchlist_intel.services.handle_summary_runtime import (
    build_handle_summary_stage,
)
from gmgn_twitter_intel.domains.watchlist_intel.types.handle_summary_agent import (
    HANDLE_SUMMARY_PAYLOAD_TYPE,
    PROMPT_VERSION,
    SCHEMA_VERSION,
)
from gmgn_twitter_intel.platform.agent_execution import (
    RUNTIME_VERSION,
    AgentCapacityReservation,
)
from gmgn_twitter_intel.platform.agent_hashing import artifact_hash_for, json_sha256


class LiteLLMWatchlistSummaryClient:
    provider = "litellm"

    def __init__(
        self,
        *,
        agent_gateway: Any,
    ) -> None:
        if agent_gateway is None:
            raise ValueError("agent_gateway is required")
        self._agent_gateway = agent_gateway

    @property
    def model(self) -> str:
        return self._agent_gateway.model_for_lane("watchlist.handle_summary")

    @property
    def artifact_version_hash(self) -> str:
        return artifact_hash_for(
            model=self.model,
            prompt_version=PROMPT_VERSION,
            schema_version=SCHEMA_VERSION,
            runtime_version=RUNTIME_VERSION,
            output_schema_hash=json_sha256(HANDLE_SUMMARY_PAYLOAD_TYPE.model_json_schema()),
        )

    def try_reserve_execution(self, lane: str, *, rate_units: int = 1) -> AgentCapacityReservation:
        return self._agent_gateway.try_reserve(lane, rate_units=rate_units)

    def request_audit(
        self,
        *,
        handle: str,
        events: list[dict[str, Any]],
        run_id: str,
        job: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        stage = build_handle_summary_stage(
            handle=handle,
            events=events,
            run_id=run_id,
            job=job,
            context=context,
        )
        return self._agent_gateway.request_audit(stage).model_dump(mode="json")

    async def summarize_handle(
        self,
        *,
        handle: str,
        events: list[dict[str, Any]],
        run_id: str,
        job: dict[str, Any],
        context: dict[str, Any],
        reservation: AgentCapacityReservation | None = None,
    ) -> dict[str, Any]:
        stage = build_handle_summary_stage(
            handle=handle,
            events=events,
            run_id=run_id,
            job=job,
            context=context,
        )
        execution = await self._agent_gateway.execute(stage, reservation=reservation)
        payload = _coerce_summary_payload(execution.final_output)
        output_json = payload.model_dump(mode="json")
        return {
            **output_json,
            "agent_run_audit": execution.audit.model_dump(mode="json"),
        }

    async def aclose(self) -> None:
        return None


def _coerce_summary_payload(value: Any) -> Any:
    if isinstance(value, HANDLE_SUMMARY_PAYLOAD_TYPE):
        return value
    return HANDLE_SUMMARY_PAYLOAD_TYPE.model_validate(value)


__all__ = ["LiteLLMWatchlistSummaryClient"]
