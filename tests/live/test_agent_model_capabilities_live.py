from __future__ import annotations

import asyncio
import os

import pytest
from pydantic import BaseModel

from parallax.integrations.model_execution.execution_gateway import AgentExecutionGateway
from parallax.platform.agent_execution import (
    AGENT_RUNTIME_LANE,
    AgentRuntimePolicy,
    AgentStageSpec,
)
from parallax.platform.config.settings import load_settings

pytestmark = pytest.mark.live


class ProbePayload(BaseModel):
    ok: bool
    label: str


def test_live_deepseek_v4_flash_json_object_strategy() -> None:
    if os.environ.get("GMGN_LIVE_LLM_SMOKE") != "1":
        pytest.skip("set GMGN_LIVE_LLM_SMOKE=1 to run live LLM smoke tests")

    async def scenario() -> None:
        settings = load_settings(require_ws_token=False)
        gateway = AgentExecutionGateway(
            api_key=settings.llm.api_key or "",
            base_url=settings.llm.base_url,
            policy=AgentRuntimePolicy(
                model="deepseek-v4-flash",
                max_concurrency=1,
                rpm_limit=60,
                timeout_seconds=45,
            ),
        )
        result = await gateway.execute(
            AgentStageSpec(
                lane=AGENT_RUNTIME_LANE,
                stage="probe",
                instructions="Return JSON with ok=true and label='probe'.",
                input_payload={"label": "probe"},
                output_type=ProbePayload,
                prompt_version="probe-v1",
                schema_version="probe-v1",
                workflow_name="parallax.probe",
                agent_name="ProbeAgent",
            )
        )

        assert result.final_output == ProbePayload(ok=True, label="probe")
        assert result.audit.model == "deepseek-v4-flash"
        assert result.audit.output_strategy == "json_object"
        assert result.audit.schema_enforcement == "client_validate"
        assert result.audit.parse_mode == "json_object_client_validate"

    asyncio.run(scenario())
