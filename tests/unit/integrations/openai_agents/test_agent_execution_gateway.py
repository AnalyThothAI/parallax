from __future__ import annotations

import asyncio
from typing import Any

import pytest
from pydantic import BaseModel

from gmgn_twitter_intel.integrations.openai_agents.agent_execution_gateway import AgentExecutionGateway
from gmgn_twitter_intel.integrations.openai_agents.instructor_safety_net import InstructorSafetyNet
from gmgn_twitter_intel.platform.agent_execution import (
    AgentCapacityReservation,
    AgentExecutionCancelled,
    AgentExecutionError,
    AgentExecutionErrorClass,
    AgentExecutionStatus,
    AgentLanePolicy,
    AgentRuntimeDefaultsPolicy,
    AgentRuntimePolicy,
    AgentStageSpec,
)


class Payload(BaseModel):
    value: str


class FakeAgent:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.name = kwargs.get("name")
        self.instructions = kwargs.get("instructions")


class FakeModel:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs


class FakeResult:
    def __init__(self, final_output: Any) -> None:
        self.final_output = final_output
        self.usage = {"input_tokens": 3, "output_tokens": 4}


class FakeRunner:
    def __init__(
        self,
        *,
        delay_seconds: float = 0,
        exception: BaseException | None = None,
        entered: asyncio.Event | None = None,
    ) -> None:
        self.calls = 0
        self.delay_seconds = delay_seconds
        self.exception = exception
        self.entered = entered
        self.run_configs: list[Any] = []
        self.input_payloads: list[Any] = []

    async def run(self, agent: Any, input_payload: Any, *, max_turns: int, run_config: Any) -> FakeResult:
        _ = agent, max_turns
        self.calls += 1
        self.input_payloads.append(input_payload)
        self.run_configs.append(run_config)
        if self.entered is not None:
            self.entered.set()
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        if self.exception is not None:
            raise self.exception
        return FakeResult(Payload(value="ok"))


class FakeLLMGateway:
    trace_export_enabled = False

    def __init__(self) -> None:
        self.openai_client_calls: list[dict[str, Any]] = []

    def openai_client(self, *, model: str, base_url: str, timeout_s: float) -> object:
        self.openai_client_calls.append({"model": model, "base_url": base_url, "timeout_s": timeout_s})
        return object()


class FakeJsonMessage:
    content = '{"value":"json-object"}'


class FakeJsonChoice:
    message = FakeJsonMessage()


class FakeJsonResponse:
    def __init__(self) -> None:
        self.choices = [FakeJsonChoice()]
        self.usage = {"prompt_tokens": 3, "completion_tokens": 2}


class FakeJsonCompletions:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> FakeJsonResponse:
        self.calls.append(kwargs)
        return FakeJsonResponse()


class FakeJsonChat:
    def __init__(self) -> None:
        self.completions = FakeJsonCompletions()


class FakeJsonClient:
    def __init__(self) -> None:
        self.chat = FakeJsonChat()


class FakeJsonLLMGateway(FakeLLMGateway):
    def __init__(self) -> None:
        super().__init__()
        self.client = FakeJsonClient()

    def openai_client(self, *, model: str, base_url: str, timeout_s: float) -> object:
        self.openai_client_calls.append({"model": model, "base_url": base_url, "timeout_s": timeout_s})
        return self.client


@pytest.fixture(autouse=True)
def _patch_sdk_constructors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "gmgn_twitter_intel.integrations.openai_agents.structured_output_strategy.Agent",
        FakeAgent,
    )
    monkeypatch.setattr(
        "gmgn_twitter_intel.integrations.openai_agents.agent_execution_gateway.OpenAIChatCompletionsModel",
        FakeModel,
    )


def _spec(lane: str = "test.lane") -> AgentStageSpec:
    return AgentStageSpec(
        lane=lane,
        stage="stage",
        instructions="Return JSON.",
        input_payload={"x": 1},
        output_type=Payload,
        prompt_version="p1",
        schema_version="s1",
        workflow_name="workflow",
        agent_name="agent",
        group_id="g1",
        trace_metadata={"source": "unit"},
    )


def _policy(*, timeout_seconds: float = 10, failure_threshold: int = 5) -> AgentRuntimePolicy:
    return AgentRuntimePolicy(
        defaults=AgentRuntimeDefaultsPolicy(model="local-schema-model"),
        global_max_concurrency=1,
        global_rpm_limit=1000,
        lanes={
            "test.lane": AgentLanePolicy(
                max_concurrency=1,
                timeout_seconds=timeout_seconds,
                circuit_breaker={
                    "failure_threshold": failure_threshold,
                    "window_seconds": 60,
                    "open_seconds": 60,
                },
            )
        },
    )


def _pulse_policy() -> AgentRuntimePolicy:
    return AgentRuntimePolicy(
        defaults=AgentRuntimeDefaultsPolicy(model="local-schema-model"),
        global_max_concurrency=1,
        global_rpm_limit=1000,
        lanes={
            "pulse.pipeline": AgentLanePolicy(max_concurrency=1, timeout_seconds=10),
            "pulse.signal_analyst": AgentLanePolicy(max_concurrency=1, timeout_seconds=10),
            "pulse.bear_case": AgentLanePolicy(max_concurrency=1, timeout_seconds=10),
            "pulse.risk_portfolio_judge": AgentLanePolicy(max_concurrency=1, timeout_seconds=10),
        },
    )


def _lane_rpm_policy() -> AgentRuntimePolicy:
    return AgentRuntimePolicy(
        defaults=AgentRuntimeDefaultsPolicy(model="local-schema-model"),
        global_max_concurrency=2,
        global_rpm_limit=1000,
        lanes={
            "test.lane": AgentLanePolicy(
                max_concurrency=2,
                timeout_seconds=10,
                rpm_limit=1,
            )
        },
    )


def _json_object_policy() -> AgentRuntimePolicy:
    return AgentRuntimePolicy(
        defaults=AgentRuntimeDefaultsPolicy(model="qwen3.6"),
        global_max_concurrency=1,
        global_rpm_limit=1000,
        lanes={
            "test.lane": AgentLanePolicy(
                model="deepseek-v4-flash",
                provider_family="deepseek",
                output_strategy="json_object",
                schema_enforcement="client_validate",
                max_concurrency=1,
                timeout_seconds=10,
            )
        },
    )


def test_execute_returns_normalized_audit_using_fake_runner() -> None:
    async def scenario() -> None:
        runner = FakeRunner()
        llm_gateway = FakeLLMGateway()
        gateway = AgentExecutionGateway(
            llm_gateway=llm_gateway,
            base_url="https://example.com/v1",
            trace_enabled=False,
            trace_include_sensitive_data=False,
            policy=_policy(),
            runner=runner,
        )

        result = await gateway.execute(_spec())

        assert isinstance(result.final_output, Payload)
        assert result.audit.status is AgentExecutionStatus.DONE
        assert result.audit.execution_started is True
        assert result.audit.usage == {"input_tokens": 3, "output_tokens": 4}
        assert result.audit.parse_mode == "strict"
        assert result.audit.safety_net == {"safety_net_used": False, "safety_net_retries": 0}
        assert result.audit.output_hash is not None
        assert result.audit.trace_metadata["source"] == "unit"
        assert runner.calls == 1
        assert runner.input_payloads == ['{"x": 1}']
        assert llm_gateway.openai_client_calls == [
            {"model": "local-schema-model", "base_url": "https://example.com/v1", "timeout_s": 10.0}
        ]

    asyncio.run(scenario())


def test_try_reserve_denies_when_lane_full_and_releases_idempotently() -> None:
    async def scenario() -> None:
        gateway = AgentExecutionGateway(
            llm_gateway=FakeLLMGateway(),
            base_url="https://example.com/v1",
            trace_enabled=False,
            trace_include_sensitive_data=False,
            policy=_policy(),
            runner=FakeRunner(),
        )

        first = gateway.try_reserve("test.lane")
        second = gateway.try_reserve("test.lane")

        assert first.acquired is True
        assert second.acquired is False
        assert second.reason is AgentExecutionErrorClass.CAPACITY_DENIED

        await first.release()
        assert first.acquired is False
        await first.release()
        assert first.acquired is False
        third = gateway.try_reserve("test.lane")
        assert third.acquired is True
        await third.release()

    asyncio.run(scenario())


def test_execute_uses_caller_reservation_without_double_acquiring_lane_capacity() -> None:
    async def scenario() -> None:
        runner = FakeRunner()
        gateway = AgentExecutionGateway(
            llm_gateway=FakeLLMGateway(),
            base_url="https://example.com/v1",
            trace_enabled=False,
            trace_include_sensitive_data=False,
            policy=_policy(),
            runner=runner,
        )
        reservation = gateway.try_reserve("test.lane")

        try:
            result = await gateway.execute(_spec(), reservation=reservation)
            snapshot_while_reserved = gateway.status_snapshot()
            assert snapshot_while_reserved["global_in_flight"] == 1
            assert snapshot_while_reserved["lanes"]["test.lane"]["in_flight"] == 1
        finally:
            await reservation.release()

        assert result.audit.status is AgentExecutionStatus.DONE
        assert runner.calls == 1
        snapshot_after_release = gateway.status_snapshot()
        assert snapshot_after_release["global_in_flight"] == 0
        assert snapshot_after_release["lanes"]["test.lane"]["in_flight"] == 0

    asyncio.run(scenario())


def test_parent_pipeline_reservation_reuses_global_slot_for_child_stage() -> None:
    async def scenario() -> None:
        runner = FakeRunner()
        gateway = AgentExecutionGateway(
            llm_gateway=FakeLLMGateway(),
            base_url="https://example.com/v1",
            trace_enabled=False,
            trace_include_sensitive_data=False,
            policy=_pulse_policy(),
            runner=runner,
        )
        parent = gateway.try_reserve(
            "pulse.pipeline",
            child_lanes=("pulse.signal_analyst", "pulse.bear_case", "pulse.risk_portfolio_judge"),
            scope="parent",
        )

        try:
            assert parent.acquired is True
            result = await gateway.execute(
                _spec("pulse.signal_analyst"),
                parent_reservation=parent,
            )
            assert result.audit.status == AgentExecutionStatus.DONE
            assert gateway.status_snapshot()["global_in_flight"] == 1
        finally:
            await parent.release()

        snapshot = gateway.status_snapshot()
        assert snapshot["global_in_flight"] == 0
        assert snapshot["lanes"]["pulse.pipeline"]["in_flight"] == 0
        assert snapshot["lanes"]["pulse.signal_analyst"]["in_flight"] == 0
        assert runner.calls == 1

    asyncio.run(scenario())


def test_lane_rpm_limit_applies_even_when_global_rpm_is_high() -> None:
    async def scenario() -> None:
        runner = FakeRunner()
        gateway = AgentExecutionGateway(
            llm_gateway=FakeLLMGateway(),
            base_url="https://example.com/v1",
            trace_enabled=False,
            trace_include_sensitive_data=False,
            policy=_lane_rpm_policy(),
            runner=runner,
        )

        first = await gateway.execute(_spec())
        assert first.audit.status is AgentExecutionStatus.DONE

        with pytest.raises(AgentExecutionError) as err:
            await gateway.execute(_spec())

        assert err.value.error_class is AgentExecutionErrorClass.RATE_LIMITED
        assert err.value.execution_started is False
        assert runner.calls == 1
        snapshot = gateway.status_snapshot()
        lane = snapshot["lanes"]["test.lane"]
        assert snapshot["global_in_flight"] == 0
        assert snapshot["global_rpm_limit"] == 1000
        assert lane["rpm_limit"] == 1
        assert lane["provider_running"] == 0
        assert lane["rpm_waiting_count"] == 0
        assert lane["in_flight"] == 0

    asyncio.run(scenario())


def test_execute_rejects_invalid_reservation_before_provider_call() -> None:
    async def scenario() -> None:
        runner = FakeRunner()
        gateway = AgentExecutionGateway(
            llm_gateway=FakeLLMGateway(),
            base_url="https://example.com/v1",
            trace_enabled=False,
            trace_include_sensitive_data=False,
            policy=_policy(),
            runner=runner,
        )

        with pytest.raises(ValueError, match="reservation lane"):
            await gateway.execute(
                _spec(),
                reservation=AgentCapacityReservation(lane="other.lane", acquired=True),
            )

        with pytest.raises(ValueError, match="acquired reservation"):
            await gateway.execute(
                _spec(),
                reservation=AgentCapacityReservation(
                    lane="test.lane",
                    acquired=False,
                    reason=AgentExecutionErrorClass.CAPACITY_DENIED,
                ),
            )

        assert runner.calls == 0

    asyncio.run(scenario())


def test_execute_rejects_released_reservation_before_provider_call() -> None:
    async def scenario() -> None:
        runner = FakeRunner()
        gateway = AgentExecutionGateway(
            llm_gateway=FakeLLMGateway(),
            base_url="https://example.com/v1",
            trace_enabled=False,
            trace_include_sensitive_data=False,
            policy=_policy(),
            runner=runner,
        )
        reservation = gateway.try_reserve("test.lane")
        await reservation.release()

        with pytest.raises(ValueError, match="active acquired reservation"):
            await gateway.execute(_spec(), reservation=reservation)

        assert runner.calls == 0

    asyncio.run(scenario())


def test_execute_rejects_manual_acquired_reservation_before_provider_call() -> None:
    async def scenario() -> None:
        runner = FakeRunner()
        gateway = AgentExecutionGateway(
            llm_gateway=FakeLLMGateway(),
            base_url="https://example.com/v1",
            trace_enabled=False,
            trace_include_sensitive_data=False,
            policy=_policy(),
            runner=runner,
        )

        with pytest.raises(ValueError, match="not issued by this gateway"):
            await gateway.execute(
                _spec(),
                reservation=AgentCapacityReservation(lane="test.lane", acquired=True),
            )

        assert runner.calls == 0

    asyncio.run(scenario())


def test_execute_rejects_other_gateway_reservation_before_provider_call() -> None:
    async def scenario() -> None:
        runner = FakeRunner()
        gateway = AgentExecutionGateway(
            llm_gateway=FakeLLMGateway(),
            base_url="https://example.com/v1",
            trace_enabled=False,
            trace_include_sensitive_data=False,
            policy=_policy(),
            runner=runner,
        )
        other_gateway = AgentExecutionGateway(
            llm_gateway=FakeLLMGateway(),
            base_url="https://example.com/v1",
            trace_enabled=False,
            trace_include_sensitive_data=False,
            policy=_policy(),
            runner=FakeRunner(),
        )
        reservation = other_gateway.try_reserve("test.lane")

        try:
            with pytest.raises(ValueError, match="not issued by this gateway"):
                await gateway.execute(_spec(), reservation=reservation)
        finally:
            await reservation.release()

        assert runner.calls == 0

    asyncio.run(scenario())


def test_execute_reuses_model_client_for_same_stage_policy() -> None:
    async def scenario() -> None:
        runner = FakeRunner()
        llm_gateway = FakeLLMGateway()
        gateway = AgentExecutionGateway(
            llm_gateway=llm_gateway,
            base_url="https://example.com/v1",
            trace_enabled=False,
            trace_include_sensitive_data=False,
            policy=_policy(),
            runner=runner,
        )

        await gateway.execute(_spec())
        await gateway.execute(_spec())

        assert runner.calls == 2
        assert llm_gateway.openai_client_calls == [
            {"model": "local-schema-model", "base_url": "https://example.com/v1", "timeout_s": 10.0}
        ]

    asyncio.run(scenario())


def test_execute_uses_json_object_strategy_for_lane_capability() -> None:
    async def scenario() -> None:
        llm_gateway = FakeJsonLLMGateway()
        gateway = AgentExecutionGateway(
            llm_gateway=llm_gateway,
            base_url="https://example.com/v1",
            trace_enabled=False,
            trace_include_sensitive_data=False,
            policy=_json_object_policy(),
            runner=FakeRunner(),
        )

        result = await gateway.execute(_spec())

        assert result.final_output == Payload(value="json-object")
        assert result.audit.model == "deepseek-v4-flash"
        assert result.audit.provider_family == "deepseek"
        assert result.audit.output_strategy == "json_object"
        assert result.audit.schema_enforcement == "client_validate"
        assert result.audit.parse_mode == "json_object_client_validate"
        assert llm_gateway.openai_client_calls == [
            {"model": "deepseek-v4-flash", "base_url": "https://example.com/v1", "timeout_s": 10.0}
        ]
        call = llm_gateway.client.chat.completions.calls[0]
        assert call["response_format"] == {"type": "json_object"}
        assert call["extra_body"] == {"thinking": {"type": "disabled"}}
        assert "tool_choice" not in call

    asyncio.run(scenario())


def test_safety_net_path_uses_injected_runner_and_returns_safety_metadata() -> None:
    async def scenario() -> None:
        runner = FakeRunner()
        gateway = AgentExecutionGateway(
            llm_gateway=FakeLLMGateway(),
            base_url="https://example.com/v1",
            trace_enabled=False,
            trace_include_sensitive_data=False,
            policy=_policy(),
            runner=runner,
            safety_net=InstructorSafetyNet(
                base_url="https://example.com/v1",
                api_key="test-key",
                model="qwen3.6",
                runner=runner,
            ),
        )

        result = await gateway.execute(_spec())

        assert isinstance(result.final_output, Payload)
        assert runner.calls == 1
        assert runner.input_payloads == ['{"x": 1}']
        assert result.audit.parse_mode == "strict"
        assert result.audit.safety_net == {"safety_net_used": False, "safety_net_retries": 0}
        assert result.audit.trace_metadata["safety_net_used"] is False
        assert result.audit.trace_metadata["parse_mode"] == "strict"

    asyncio.run(scenario())


def test_circuit_open_fails_fast_without_runner_call_after_threshold_one_failure() -> None:
    async def scenario() -> None:
        runner = FakeRunner()
        gateway = AgentExecutionGateway(
            llm_gateway=FakeLLMGateway(),
            base_url="https://example.com/v1",
            trace_enabled=False,
            trace_include_sensitive_data=False,
            policy=_policy(failure_threshold=1),
            runner=runner,
        )
        gateway.record_lane_failure("test.lane")

        with pytest.raises(AgentExecutionError) as err:
            await gateway.execute(_spec())

        assert err.value.error_class is AgentExecutionErrorClass.CIRCUIT_OPEN
        assert err.value.execution_started is False
        assert err.value.audit is not None
        assert err.value.audit.execution_started is False
        assert runner.calls == 0

    asyncio.run(scenario())


def test_timeout_maps_to_execution_error_with_started_audit() -> None:
    async def scenario() -> None:
        runner = FakeRunner(delay_seconds=2)
        gateway = AgentExecutionGateway(
            llm_gateway=FakeLLMGateway(),
            base_url="https://example.com/v1",
            trace_enabled=False,
            trace_include_sensitive_data=False,
            policy=_policy(timeout_seconds=1),
            runner=runner,
        )

        with pytest.raises(AgentExecutionError) as err:
            await gateway.execute(_spec())

        assert err.value.error_class is AgentExecutionErrorClass.TIMEOUT
        assert err.value.execution_started is True
        assert err.value.audit is not None
        assert err.value.audit.status is AgentExecutionStatus.FAILED
        assert err.value.audit.execution_started is True
        assert err.value.audit.error_class is AgentExecutionErrorClass.TIMEOUT
        assert runner.calls == 1

    asyncio.run(scenario())


def test_status_snapshot_includes_lane_counters() -> None:
    async def scenario() -> None:
        gateway = AgentExecutionGateway(
            llm_gateway=FakeLLMGateway(),
            base_url="https://example.com/v1",
            trace_enabled=False,
            trace_include_sensitive_data=False,
            policy=_policy(failure_threshold=1),
            runner=FakeRunner(),
        )

        reservation = gateway.try_reserve("test.lane")
        denied = gateway.try_reserve("test.lane")
        gateway.record_lane_failure("test.lane")
        snapshot = gateway.status_snapshot()

        assert reservation.acquired is True
        assert denied.reason is AgentExecutionErrorClass.CAPACITY_DENIED
        assert snapshot["global_max_concurrency"] == 1
        assert snapshot["global_in_flight"] == 1
        assert snapshot["lanes"]["test.lane"]["max_concurrency"] == 1
        assert snapshot["lanes"]["test.lane"]["timeout_seconds"] == 10.0
        assert snapshot["lanes"]["test.lane"]["in_flight"] == 1
        assert snapshot["lanes"]["test.lane"]["circuit_state"] == "open"
        assert snapshot["lanes"]["test.lane"]["capacity_denied_total"] == 1
        assert snapshot["lanes"]["test.lane"]["circuit_open_total"] == 0
        assert snapshot["lanes"]["test.lane"]["timeout_total"] == 0

        await reservation.release()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("runner", "expected_error"),
    [
        (FakeRunner(), None),
        (
            FakeRunner(
                exception=AgentExecutionError(
                    AgentExecutionErrorClass.PROVIDER_ERROR,
                    "provider failed",
                    execution_started=True,
                )
            ),
            AgentExecutionError,
        ),
        (FakeRunner(exception=RuntimeError("boom")), AgentExecutionError),
    ],
)
def test_execute_releases_internal_reservation_after_success_and_errors(
    runner: FakeRunner,
    expected_error: type[BaseException] | None,
) -> None:
    async def scenario() -> None:
        gateway = AgentExecutionGateway(
            llm_gateway=FakeLLMGateway(),
            base_url="https://example.com/v1",
            trace_enabled=False,
            trace_include_sensitive_data=False,
            policy=_policy(),
            runner=runner,
        )

        if expected_error is None:
            await gateway.execute(_spec())
        else:
            with pytest.raises(expected_error):
                await gateway.execute(_spec())

        snapshot = gateway.status_snapshot()
        assert snapshot["global_in_flight"] == 0
        assert snapshot["lanes"]["test.lane"]["in_flight"] == 0

    asyncio.run(scenario())


def test_execute_releases_internal_reservation_after_cancellation() -> None:
    async def scenario() -> None:
        entered = asyncio.Event()
        runner = FakeRunner(delay_seconds=60, entered=entered)
        gateway = AgentExecutionGateway(
            llm_gateway=FakeLLMGateway(),
            base_url="https://example.com/v1",
            trace_enabled=False,
            trace_include_sensitive_data=False,
            policy=_policy(),
            runner=runner,
        )

        task = asyncio.create_task(gateway.execute(_spec()))
        await asyncio.wait_for(entered.wait(), timeout=1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        snapshot = gateway.status_snapshot()
        assert snapshot["global_in_flight"] == 0
        assert snapshot["lanes"]["test.lane"]["in_flight"] == 0

    asyncio.run(scenario())


def test_gateway_supervisor_cancellation_records_cancelled_audit_and_releases_reservation() -> None:
    async def scenario() -> None:
        entered = asyncio.Event()
        runner = FakeRunner(delay_seconds=60, entered=entered)
        gateway = AgentExecutionGateway(
            llm_gateway=FakeLLMGateway(),
            base_url="https://example.com/v1",
            trace_enabled=False,
            trace_include_sensitive_data=False,
            policy=_policy(),
            runner=runner,
        )

        task = asyncio.create_task(gateway.execute(_spec()))
        await asyncio.wait_for(entered.wait(), timeout=1)
        running_snapshot = gateway.status_snapshot()
        assert running_snapshot["global_in_flight"] == 1
        assert running_snapshot["lanes"]["test.lane"]["in_flight"] == 1
        assert running_snapshot["lanes"]["test.lane"]["provider_running"] == 1

        task.cancel()
        exceptions = await asyncio.gather(task, return_exceptions=True)

        assert len(exceptions) == 1
        assert isinstance(exceptions[0], asyncio.CancelledError)
        with pytest.raises(AgentExecutionCancelled) as err:
            await task
        exc = err.value
        assert exc.audit is not None
        assert exc.audit.error_class is AgentExecutionErrorClass.CANCELLED
        assert exc.audit.status is AgentExecutionStatus.FAILED
        assert exc.execution_started is True
        assert exc.audit.execution_started is True
        snapshot = gateway.status_snapshot()
        assert snapshot["global_in_flight"] == 0
        assert snapshot["lanes"]["test.lane"]["in_flight"] == 0
        assert snapshot["lanes"]["test.lane"]["provider_running"] == 0

    asyncio.run(scenario())
