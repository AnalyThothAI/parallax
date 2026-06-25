from __future__ import annotations

import asyncio
from typing import Any

import pytest
from pydantic import BaseModel

from parallax.integrations.model_execution.execution_gateway import (
    AgentExecutionGateway,
    _llm_gateway_bool,
    _llm_gateway_text,
    _safety_net_retries,
)
from parallax.integrations.model_execution.output_schema import StrictJsonOutputSchema
from parallax.platform.agent_execution import (
    RUNTIME_VERSION,
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
from parallax.platform.agent_hashing import artifact_hash_for, json_sha256, text_sha256


class Payload(BaseModel):
    value: str


class FakeJsonMessage:
    def __init__(self, content: str = '{"value":"json-object"}') -> None:
        self.content = content


class FakeJsonChoice:
    def __init__(self, content: str = '{"value":"json-object"}') -> None:
        self.message = FakeJsonMessage(content)


class FakeJsonResponse:
    def __init__(self, content: str = '{"value":"json-object"}') -> None:
        self.choices = [FakeJsonChoice(content)]
        self.usage = {"prompt_tokens": 3, "completion_tokens": 2}


class FakeJsonCompletions:
    def __init__(
        self,
        *,
        content: str = '{"value":"json-object"}',
        delay_seconds: float = 0,
        exception: BaseException | None = None,
        entered: asyncio.Event | None = None,
    ) -> None:
        self.calls: list[dict[str, Any]] = []
        self.content = content
        self.delay_seconds = delay_seconds
        self.exception = exception
        self.entered = entered

    async def create(self, **kwargs: Any) -> FakeJsonResponse:
        self.calls.append(kwargs)
        if self.entered is not None:
            self.entered.set()
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        if self.exception is not None:
            raise self.exception
        return FakeJsonResponse(self.content)


class FakeJsonChat:
    def __init__(self, completions: FakeJsonCompletions) -> None:
        self.completions = completions


class FakeJsonClient:
    def __init__(self, completions: FakeJsonCompletions | None = None) -> None:
        self.chat = FakeJsonChat(completions or FakeJsonCompletions())


class FakeLLMGateway:
    trace_export_enabled = False

    def __init__(self, *, completions: FakeJsonCompletions | None = None) -> None:
        self.api_key = "sk-test"
        self.base_url = "https://example.com/v1"
        self.completions = completions or FakeJsonCompletions()


_active_completions: list[FakeJsonCompletions | None] = [None]


@pytest.fixture(autouse=True)
def patch_litellm(monkeypatch: pytest.MonkeyPatch):
    async def fake_acompletion(**kwargs: Any) -> FakeJsonResponse:
        completions = _active_completions[0]
        if completions is None:
            raise AssertionError("active fake LiteLLM completion not configured")
        return await completions.create(**kwargs)

    monkeypatch.setattr(
        "parallax.integrations.model_execution.structured_json_strategy.litellm.acompletion",
        fake_acompletion,
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
        defaults=AgentRuntimeDefaultsPolicy(model="local-json-object-model"),
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


def _parent_child_policy() -> AgentRuntimePolicy:
    return AgentRuntimePolicy(
        defaults=AgentRuntimeDefaultsPolicy(model="local-json-object-model"),
        global_max_concurrency=2,
        global_rpm_limit=1000,
        lanes={
            "test.parent": AgentLanePolicy(max_concurrency=2, timeout_seconds=10),
            "test.child": AgentLanePolicy(max_concurrency=1, timeout_seconds=10),
        },
    )


def _lane_rpm_policy() -> AgentRuntimePolicy:
    return AgentRuntimePolicy(
        defaults=AgentRuntimeDefaultsPolicy(model="local-json-object-model"),
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


def _deepseek_policy(*, max_tokens: int | None = None) -> AgentRuntimePolicy:
    return AgentRuntimePolicy(
        defaults=AgentRuntimeDefaultsPolicy(model="qwen3.6"),
        global_max_concurrency=1,
        global_rpm_limit=1000,
        lanes={
            "test.lane": AgentLanePolicy(
                model="deepseek-v4-flash",
                provider_family="deepseek",
                max_tokens=max_tokens,
                max_concurrency=1,
                timeout_seconds=10,
            )
        },
    )


def _gateway(
    *,
    llm_gateway: FakeLLMGateway | None = None,
    policy: AgentRuntimePolicy | None = None,
) -> AgentExecutionGateway:
    llm_gateway = llm_gateway or FakeLLMGateway()
    _active_completions[0] = llm_gateway.completions
    return AgentExecutionGateway(
        llm_gateway=llm_gateway,
        base_url="https://example.com/v1",
        trace_enabled=False,
        trace_include_sensitive_data=False,
        policy=policy or _policy(),
    )


def test_request_audit_artifact_hash_includes_stage_instructions() -> None:
    policy = _policy()
    gateway = _gateway(policy=policy)
    spec = _spec().model_copy(update={"instructions": "Return JSON with value alpha."})
    changed = spec.model_copy(update={"instructions": "Return JSON with value beta."})
    capability_profile = policy.capability_for_lane(spec.lane)
    expected_hash = artifact_hash_for(
        model=gateway.model_for_lane(spec.lane),
        provider_family=capability_profile.provider_family.value,
        request_options_hash=json_sha256(capability_profile.request_options),
        prompt_version=spec.prompt_version,
        schema_version=spec.schema_version,
        runtime_version=RUNTIME_VERSION,
        output_schema_hash=json_sha256(StrictJsonOutputSchema(spec.output_type).json_schema()),
        prompt_text_hash=text_sha256(spec.instructions),
    )

    audit = gateway.request_audit(spec)
    changed_audit = gateway.request_audit(changed)

    assert audit.artifact_version_hash == expected_hash
    assert audit.artifact_version_hash != changed_audit.artifact_version_hash


def test_gateway_defaults_missing_safety_net_retries_to_zero() -> None:
    assert _safety_net_retries({}) == 0


@pytest.mark.parametrize("safety_net_retries", [0, 2])
def test_gateway_accepts_formal_safety_net_retries(safety_net_retries: int) -> None:
    assert _safety_net_retries({"safety_net_retries": safety_net_retries}) == safety_net_retries


@pytest.mark.parametrize("safety_net_retries", [-1, True, "1"])
def test_gateway_rejects_malformed_safety_net_retries_without_cast(safety_net_retries: object) -> None:
    with pytest.raises(ValueError, match="agent_execution_safety_net_retries_required"):
        _safety_net_retries({"safety_net_retries": safety_net_retries})


def test_gateway_requires_formal_llm_gateway_text_fields_without_defaults() -> None:
    with pytest.raises(ValueError, match="agent_execution_llm_gateway_api_key_required"):
        _llm_gateway_text(object(), "api_key")

    with pytest.raises(ValueError, match="agent_execution_llm_gateway_base_url_required"):
        _llm_gateway_text(type("BadGateway", (), {"base_url": 12})(), "base_url")


def test_gateway_requires_formal_llm_gateway_bool_fields_without_defaults() -> None:
    with pytest.raises(ValueError, match="agent_execution_llm_gateway_trace_export_enabled_required"):
        _llm_gateway_bool(object(), "trace_export_enabled")

    with pytest.raises(ValueError, match="agent_execution_llm_gateway_trace_export_enabled_required"):
        _llm_gateway_bool(type("BadGateway", (), {"trace_export_enabled": "false"})(), "trace_export_enabled")


def test_execute_returns_normalized_audit_using_json_object_client() -> None:
    async def scenario() -> None:
        llm_gateway = FakeLLMGateway()
        gateway = _gateway(llm_gateway=llm_gateway)

        result = await gateway.execute(_spec())

        assert result.final_output == Payload(value="json-object")
        assert result.audit.status is AgentExecutionStatus.DONE
        assert result.audit.execution_started is True
        assert result.audit.usage == {"prompt_tokens": 3, "completion_tokens": 2}
        assert result.audit.parse_mode == "json_object_client_validate"
        assert result.audit.safety_net == {"safety_net_used": False, "safety_net_retries": 0}
        assert result.audit.output_hash is not None
        assert result.audit.trace_metadata["source"] == "unit"
        assert result.audit.trace_metadata["output_strategy"] == "json_object"
        assert result.audit.trace_metadata["schema_enforcement"] == "client_validate"
        assert len(llm_gateway.completions.calls) == 1
        assert llm_gateway.completions.calls[0]["model"] == "openai/local-json-object-model"
        assert llm_gateway.completions.calls[0]["base_url"] == "https://example.com/v1"
        assert llm_gateway.completions.calls[0]["timeout"] == 10.0

    asyncio.run(scenario())


def test_try_reserve_denies_when_lane_full_and_releases_idempotently() -> None:
    async def scenario() -> None:
        gateway = _gateway()

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
        llm_gateway = FakeLLMGateway()
        gateway = _gateway(llm_gateway=llm_gateway)
        reservation = gateway.try_reserve("test.lane")

        try:
            result = await gateway.execute(_spec(), reservation=reservation)
            snapshot_while_reserved = gateway.status_snapshot()
            assert snapshot_while_reserved["global_in_flight"] == 1
            assert snapshot_while_reserved["lanes"]["test.lane"]["in_flight"] == 1
        finally:
            await reservation.release()

        assert result.audit.status is AgentExecutionStatus.DONE
        assert len(llm_gateway.completions.calls) == 1
        snapshot_after_release = gateway.status_snapshot()
        assert snapshot_after_release["global_in_flight"] == 0
        assert snapshot_after_release["lanes"]["test.lane"]["in_flight"] == 0

    asyncio.run(scenario())


def test_parent_pipeline_reservation_reuses_global_slot_for_child_stage() -> None:
    async def scenario() -> None:
        llm_gateway = FakeLLMGateway()
        gateway = _gateway(llm_gateway=llm_gateway, policy=_parent_child_policy())
        parent = gateway.try_reserve(
            "test.parent",
            child_lanes=("test.child",),
            scope="parent",
        )

        try:
            assert parent.acquired is True
            result = await gateway.execute(
                _spec("test.child"),
                parent_reservation=parent,
            )
            assert result.audit.status == AgentExecutionStatus.DONE
            assert gateway.status_snapshot()["global_in_flight"] == 1
        finally:
            await parent.release()

        snapshot = gateway.status_snapshot()
        assert snapshot["global_in_flight"] == 0
        assert snapshot["lanes"]["test.parent"]["in_flight"] == 0
        assert snapshot["lanes"]["test.child"]["in_flight"] == 0
        assert len(llm_gateway.completions.calls) == 1

    asyncio.run(scenario())


def test_parent_pipeline_reservation_reserves_child_lane_capacity_before_claim() -> None:
    async def scenario() -> None:
        gateway = _gateway(policy=_parent_child_policy())
        first = gateway.try_reserve(
            "test.parent",
            child_lanes=("test.child",),
            scope="parent",
        )
        try:
            second = gateway.try_reserve(
                "test.parent",
                child_lanes=("test.child",),
                scope="parent",
            )

            assert first.acquired is True
            assert second.acquired is False
            assert second.reason is AgentExecutionErrorClass.CAPACITY_DENIED
            snapshot = gateway.status_snapshot()
            assert snapshot["global_in_flight"] == 1
            assert snapshot["lanes"]["test.parent"]["in_flight"] == 1
            assert snapshot["lanes"]["test.child"]["in_flight"] == 1
        finally:
            await first.release()

        snapshot = gateway.status_snapshot()
        assert snapshot["global_in_flight"] == 0
        assert snapshot["lanes"]["test.parent"]["in_flight"] == 0
        assert snapshot["lanes"]["test.child"]["in_flight"] == 0

    asyncio.run(scenario())


def test_try_reserve_denies_rpm_before_provider_execution() -> None:
    async def scenario() -> None:
        gateway = _gateway(policy=_lane_rpm_policy())
        first = gateway.try_reserve("test.lane")
        assert first.acquired is True
        await first.release()

        second = gateway.try_reserve("test.lane")

        assert second.acquired is False
        assert second.reason is AgentExecutionErrorClass.RATE_LIMITED
        snapshot = gateway.status_snapshot()
        assert snapshot["global_in_flight"] == 0
        assert snapshot["lanes"]["test.lane"]["in_flight"] == 0

    asyncio.run(scenario())


def test_try_reserve_rate_units_consume_multiple_rpm_slots_before_claim() -> None:
    async def scenario() -> None:
        policy = AgentRuntimePolicy(
            defaults=AgentRuntimeDefaultsPolicy(model="local-json-object-model"),
            global_max_concurrency=2,
            global_rpm_limit=2,
            lanes={
                "test.lane": AgentLanePolicy(
                    max_concurrency=2,
                    timeout_seconds=10,
                    rpm_limit=2,
                )
            },
        )
        gateway = _gateway(policy=policy)

        first = gateway.try_reserve("test.lane", rate_units=2)
        assert first.acquired is True
        assert first.rate_units == 2
        await first.release()

        second = gateway.try_reserve("test.lane")

        assert second.acquired is False
        assert second.reason is AgentExecutionErrorClass.RATE_LIMITED
        assert gateway.status_snapshot()["global_in_flight"] == 0

    asyncio.run(scenario())


def test_try_reserve_rejects_malformed_rate_units_before_capacity_claim() -> None:
    async def scenario() -> None:
        gateway = _gateway(policy=_lane_rpm_policy())

        for rate_units in (0, -1, True, "2"):
            with pytest.raises(ValueError, match="agent_execution_rate_units_required"):
                gateway.try_reserve("test.lane", rate_units=rate_units)  # type: ignore[arg-type]

        snapshot = gateway.status_snapshot()
        assert snapshot["global_in_flight"] == 0
        assert snapshot["lanes"]["test.lane"]["in_flight"] == 0

    asyncio.run(scenario())


def test_try_reserve_rate_units_clamps_batch_to_available_rpm_capacity() -> None:
    async def scenario() -> None:
        policy = AgentRuntimePolicy(
            defaults=AgentRuntimeDefaultsPolicy(model="local-json-object-model"),
            global_max_concurrency=2,
            global_rpm_limit=2,
            lanes={
                "test.lane": AgentLanePolicy(
                    max_concurrency=2,
                    timeout_seconds=10,
                    rpm_limit=2,
                )
            },
        )
        gateway = _gateway(policy=policy)

        reservation = gateway.try_reserve("test.lane", rate_units=5)

        assert reservation.acquired is True
        assert reservation.rate_units == 2
        await reservation.release()

    asyncio.run(scenario())


def test_lane_rpm_limit_applies_even_when_global_rpm_is_high() -> None:
    async def scenario() -> None:
        llm_gateway = FakeLLMGateway()
        gateway = _gateway(llm_gateway=llm_gateway, policy=_lane_rpm_policy())

        first = await gateway.execute(_spec())
        assert first.audit.status is AgentExecutionStatus.DONE

        with pytest.raises(AgentExecutionError) as err:
            await gateway.execute(_spec())

        assert err.value.error_class is AgentExecutionErrorClass.RATE_LIMITED
        assert err.value.execution_started is False
        assert len(llm_gateway.completions.calls) == 1
        snapshot = gateway.status_snapshot()
        lane = snapshot["lanes"]["test.lane"]
        assert snapshot["global_in_flight"] == 0
        assert snapshot["global_rpm_limit"] == 1000
        assert lane["rpm_limit"] == 1
        assert lane["provider_running"] == 0
        assert lane["rpm_waiting_count"] == 0
        assert lane["in_flight"] == 0

    asyncio.run(scenario())


def test_execute_rejects_invalid_reservations_before_provider_call() -> None:
    async def scenario() -> None:
        llm_gateway = FakeLLMGateway()
        gateway = _gateway(llm_gateway=llm_gateway)

        with pytest.raises(ValueError, match="reservation lane"):
            await gateway.execute(_spec(), reservation=AgentCapacityReservation(lane="other.lane", acquired=True))

        with pytest.raises(ValueError, match="acquired reservation"):
            await gateway.execute(
                _spec(),
                reservation=AgentCapacityReservation(
                    lane="test.lane",
                    acquired=False,
                    reason=AgentExecutionErrorClass.CAPACITY_DENIED,
                ),
            )

        reservation = gateway.try_reserve("test.lane")
        await reservation.release()
        with pytest.raises(ValueError, match="active acquired reservation"):
            await gateway.execute(_spec(), reservation=reservation)

        with pytest.raises(ValueError, match="not issued by this gateway"):
            await gateway.execute(_spec(), reservation=AgentCapacityReservation(lane="test.lane", acquired=True))

        assert llm_gateway.completions.calls == []

    asyncio.run(scenario())


def test_execute_rejects_other_gateway_reservation_before_provider_call() -> None:
    async def scenario() -> None:
        llm_gateway = FakeLLMGateway()
        gateway = _gateway(llm_gateway=llm_gateway)
        other_gateway = _gateway()
        reservation = other_gateway.try_reserve("test.lane")

        try:
            with pytest.raises(ValueError, match="not issued by this gateway"):
                await gateway.execute(_spec(), reservation=reservation)
        finally:
            await reservation.release()

        assert llm_gateway.completions.calls == []

    asyncio.run(scenario())


def test_execute_reuses_chat_client_for_same_stage_policy() -> None:
    async def scenario() -> None:
        llm_gateway = FakeLLMGateway()
        gateway = _gateway(llm_gateway=llm_gateway)

        await gateway.execute(_spec())
        await gateway.execute(_spec())

        assert len(llm_gateway.completions.calls) == 2
        assert [call["model"] for call in llm_gateway.completions.calls] == [
            "openai/local-json-object-model",
            "openai/local-json-object-model",
        ]

    asyncio.run(scenario())


def test_execute_uses_registered_model_request_options() -> None:
    async def scenario() -> None:
        llm_gateway = FakeLLMGateway()
        gateway = _gateway(llm_gateway=llm_gateway, policy=_deepseek_policy(max_tokens=2200))

        result = await gateway.execute(_spec())

        assert result.audit.model == "deepseek-v4-flash"
        assert result.audit.provider_family == "deepseek"
        assert result.audit.output_strategy == "json_object"
        assert result.audit.schema_enforcement == "client_validate"
        assert result.audit.parse_mode == "json_object_client_validate"
        call = llm_gateway.completions.calls[0]
        assert call["model"] == "openai/deepseek-v4-flash"
        assert call["base_url"] == "https://example.com/v1"
        assert call["timeout"] == 10.0
        assert call["response_format"] == {"type": "json_object"}
        assert call["extra_body"] == {"thinking": {"type": "disabled"}}
        assert call["max_tokens"] == 2200
        assert "tool_choice" not in call

    asyncio.run(scenario())


def test_circuit_open_fails_fast_without_provider_call() -> None:
    async def scenario() -> None:
        llm_gateway = FakeLLMGateway()
        gateway = _gateway(llm_gateway=llm_gateway, policy=_policy(failure_threshold=1))
        gateway.record_lane_failure("test.lane")

        with pytest.raises(AgentExecutionError) as err:
            await gateway.execute(_spec())

        assert err.value.error_class is AgentExecutionErrorClass.CIRCUIT_OPEN
        assert err.value.execution_started is False
        assert err.value.audit is not None
        assert err.value.audit.execution_started is False
        assert llm_gateway.completions.calls == []

    asyncio.run(scenario())


def test_insufficient_balance_is_quota_exhausted_no_start_and_opens_circuit() -> None:
    async def scenario() -> None:
        completions = FakeJsonCompletions(exception=RuntimeError("OpenAIException - Insufficient Balance"))
        gateway = _gateway(
            llm_gateway=FakeLLMGateway(completions=completions),
            policy=_policy(failure_threshold=1),
        )

        with pytest.raises(AgentExecutionError) as err:
            await gateway.execute(_spec())

        assert err.value.error_class is AgentExecutionErrorClass.QUOTA_EXHAUSTED
        assert err.value.execution_started is False
        assert len(completions.calls) == 1

        denied = gateway.try_reserve("test.lane")
        assert denied.acquired is False
        assert denied.reason is AgentExecutionErrorClass.CIRCUIT_OPEN

    asyncio.run(scenario())


@pytest.mark.parametrize("message", ["quota unavailable", "payment failed"])
def test_quota_and_payment_provider_messages_are_quota_exhausted(message: str) -> None:
    async def scenario() -> None:
        completions = FakeJsonCompletions(exception=RuntimeError(message))
        gateway = _gateway(
            llm_gateway=FakeLLMGateway(completions=completions),
            policy=_policy(failure_threshold=1),
        )

        with pytest.raises(AgentExecutionError) as err:
            await gateway.execute(_spec())

        assert err.value.error_class is AgentExecutionErrorClass.QUOTA_EXHAUSTED
        assert err.value.execution_started is False
        assert len(completions.calls) == 1

        denied = gateway.try_reserve("test.lane")
        assert denied.acquired is False
        assert denied.reason is AgentExecutionErrorClass.CIRCUIT_OPEN

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("message", "expected_error_class"),
    [
        ("rate limit: insufficient quota", AgentExecutionErrorClass.RATE_LIMITED),
        ("transport connection lost after payment check", AgentExecutionErrorClass.TRANSPORT_ERROR),
    ],
)
def test_rate_limit_and_transport_precede_quota_provider_markers(
    message: str,
    expected_error_class: AgentExecutionErrorClass,
) -> None:
    async def scenario() -> None:
        completions = FakeJsonCompletions(exception=RuntimeError(message))
        gateway = _gateway(
            llm_gateway=FakeLLMGateway(completions=completions),
            policy=_policy(failure_threshold=2),
        )

        with pytest.raises(AgentExecutionError) as err:
            await gateway.execute(_spec())

        assert err.value.error_class is expected_error_class
        assert err.value.execution_started is True
        assert len(completions.calls) == 1

        reservation = gateway.try_reserve("test.lane")
        try:
            assert reservation.acquired is True
        finally:
            await reservation.release()

    asyncio.run(scenario())


def test_timeout_maps_to_execution_error_with_started_audit() -> None:
    async def scenario() -> None:
        completions = FakeJsonCompletions(delay_seconds=2)
        llm_gateway = FakeLLMGateway(completions=completions)
        gateway = _gateway(llm_gateway=llm_gateway, policy=_policy(timeout_seconds=1))

        with pytest.raises(AgentExecutionError) as err:
            await gateway.execute(_spec())

        assert err.value.error_class is AgentExecutionErrorClass.TIMEOUT
        assert err.value.execution_started is True
        assert err.value.audit is not None
        assert err.value.audit.status is AgentExecutionStatus.FAILED
        assert err.value.audit.execution_started is True
        assert err.value.audit.error_class is AgentExecutionErrorClass.TIMEOUT
        assert len(completions.calls) == 1

    asyncio.run(scenario())


def test_status_snapshot_includes_lane_counters() -> None:
    async def scenario() -> None:
        gateway = _gateway(policy=_policy(failure_threshold=1))

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
        assert snapshot["lanes"]["test.lane"]["output_strategy"] == "json_object"
        assert snapshot["lanes"]["test.lane"]["schema_enforcement"] == "client_validate"
        assert snapshot["lanes"]["test.lane"]["in_flight"] == 1
        assert snapshot["lanes"]["test.lane"]["circuit_state"] == "open"
        assert snapshot["lanes"]["test.lane"]["capacity_denied_total"] == 1
        assert snapshot["lanes"]["test.lane"]["circuit_open_total"] == 0
        assert snapshot["lanes"]["test.lane"]["timeout_total"] == 0

        await reservation.release()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("exception", "expected_error"),
    [
        (None, None),
        (
            AgentExecutionError(
                AgentExecutionErrorClass.PROVIDER_ERROR,
                "provider failed",
                execution_started=True,
            ),
            AgentExecutionError,
        ),
        (RuntimeError("boom"), AgentExecutionError),
    ],
)
def test_execute_releases_internal_reservation_after_success_and_errors(
    exception: BaseException | None,
    expected_error: type[BaseException] | None,
) -> None:
    async def scenario() -> None:
        llm_gateway = FakeLLMGateway(completions=FakeJsonCompletions(exception=exception))
        gateway = _gateway(llm_gateway=llm_gateway)

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
        completions = FakeJsonCompletions(delay_seconds=60, entered=entered)
        gateway = _gateway(llm_gateway=FakeLLMGateway(completions=completions))

        task = asyncio.create_task(gateway.execute(_spec()))
        await asyncio.wait_for(entered.wait(), timeout=1)
        task.cancel()
        with pytest.raises(AgentExecutionCancelled):
            await task

        snapshot = gateway.status_snapshot()
        assert snapshot["global_in_flight"] == 0
        assert snapshot["lanes"]["test.lane"]["in_flight"] == 0

    asyncio.run(scenario())


def test_gateway_supervisor_cancellation_records_cancelled_audit_and_releases_reservation() -> None:
    async def scenario() -> None:
        entered = asyncio.Event()
        completions = FakeJsonCompletions(delay_seconds=60, entered=entered)
        gateway = _gateway(llm_gateway=FakeLLMGateway(completions=completions))

        task = asyncio.create_task(gateway.execute(_spec()))
        await asyncio.wait_for(entered.wait(), timeout=1)
        running_snapshot = gateway.status_snapshot()
        assert running_snapshot["global_in_flight"] == 1
        assert running_snapshot["lanes"]["test.lane"]["in_flight"] == 1
        assert running_snapshot["lanes"]["test.lane"]["provider_running"] == 1

        task.cancel()
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
