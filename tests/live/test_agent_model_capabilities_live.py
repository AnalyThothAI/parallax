from __future__ import annotations

import asyncio
import os

import pytest
from pydantic import BaseModel

from gmgn_twitter_intel.app.runtime.llm_gateway import LLMGateway
from gmgn_twitter_intel.integrations.model_execution.execution_gateway import AgentExecutionGateway
from gmgn_twitter_intel.platform.agent_execution import (
    AgentLanePolicy,
    AgentRuntimeDefaultsPolicy,
    AgentRuntimePolicy,
    AgentStageSpec,
)
from gmgn_twitter_intel.platform.config.settings import load_settings

pytestmark = pytest.mark.live


class ProbePayload(BaseModel):
    ok: bool
    label: str


def test_live_deepseek_v4_flash_json_object_strategy() -> None:
    if os.environ.get("GMGN_LIVE_LLM_SMOKE") != "1":
        pytest.skip("set GMGN_LIVE_LLM_SMOKE=1 to run live LLM smoke tests")

    async def scenario() -> None:
        settings = load_settings(require_ws_token=False)
        llm_gateway = LLMGateway.create(settings)
        gateway = AgentExecutionGateway(
            llm_gateway=llm_gateway,
            base_url=settings.llm_base_url,
            trace_enabled=False,
            trace_include_sensitive_data=False,
            policy=AgentRuntimePolicy(
                defaults=AgentRuntimeDefaultsPolicy(model="deepseek-v4-flash"),
                global_max_concurrency=1,
                global_rpm_limit=60,
                lanes={"probe.deepseek": AgentLanePolicy(timeout_seconds=45)},
            ),
        )
        try:
            result = await gateway.execute(
                AgentStageSpec(
                    lane="probe.deepseek",
                    stage="probe",
                    instructions="Return JSON with ok=true and label='probe'.",
                    input_payload={"label": "probe"},
                    output_type=ProbePayload,
                    prompt_version="probe-v1",
                    schema_version="probe-v1",
                    workflow_name="gmgn-twitter-intel.probe",
                    agent_name="ProbeAgent",
                )
            )
        finally:
            await gateway.aclose()
            await llm_gateway.aclose()

        assert result.final_output == ProbePayload(ok=True, label="probe")
        assert result.audit.model == "deepseek-v4-flash"
        assert result.audit.output_strategy == "json_object"
        assert result.audit.schema_enforcement == "client_validate"
        assert result.audit.parse_mode == "json_object_client_validate"

    asyncio.run(scenario())
