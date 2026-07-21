from __future__ import annotations

import asyncio
from typing import Any

import pytest
from pydantic import BaseModel

from parallax.integrations.model_execution.execution_gateway import AgentExecutionGateway
from parallax.integrations.model_execution.output_schema import StrictJsonOutputSchema
from parallax.platform.agent_execution import (
    AGENT_RUNTIME_LANE,
    RUNTIME_VERSION,
    AgentCapacityReservation,
    AgentExecutionCancelled,
    AgentExecutionError,
    AgentExecutionErrorClass,
    AgentExecutionStatus,
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


class FakeModelBackend:
    def __init__(self, *, completions: FakeJsonCompletions | None = None) -> None:
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


def _spec() -> AgentStageSpec:
    return AgentStageSpec(
        lane=AGENT_RUNTIME_LANE,
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
        model="local-json-object-model",
        max_concurrency=1,
        rpm_limit=1000,
        timeout_seconds=timeout_seconds,
        circuit_breaker={
            "failure_threshold": failure_threshold,
            "window_seconds": 60,
            "open_seconds": 60,
        },
    )


def _lane_rpm_policy() -> AgentRuntimePolicy:
    return AgentRuntimePolicy(
        model="local-json-object-model",
        max_concurrency=2,
        rpm_limit=1,
        timeout_seconds=10,
    )


def _deepseek_policy(*, max_tokens: int = 2200) -> AgentRuntimePolicy:
    return AgentRuntimePolicy(
        model="deepseek-v4-flash",
        provider_family="deepseek",
        max_tokens=max_tokens,
        max_concurrency=1,
        rpm_limit=1000,
        timeout_seconds=10,
    )


def _gateway(
    *,
    llm_gateway: FakeModelBackend | None = None,
    policy: AgentRuntimePolicy | None = None,
) -> AgentExecutionGateway:
    llm_gateway = llm_gateway or FakeModelBackend()
    _active_completions[0] = llm_gateway.completions
    return AgentExecutionGateway(
        api_key="sk-test",
        base_url="https://example.com/v1",
        policy=policy or _policy(),
    )


def test_request_audit_artifact_hash_includes_stage_instructions() -> None:
    policy = _policy()
    gateway = _gateway(policy=policy)
    spec = _spec().model_copy(update={"instructions": "Return JSON with value alpha."})
    changed = spec.model_copy(update={"instructions": "Return JSON with value beta."})
    capability_profile = policy.capability_profile()
    expected_hash = artifact_hash_for(
        model=gateway.model,
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


def test_execute_returns_normalized_audit_using_json_object_client() -> None:
    async def scenario() -> None:
        llm_gateway = FakeModelBackend()
        gateway = _gateway(llm_gateway=llm_gateway)

        result = await gateway.execute(_spec())

        assert result.final_output == Payload(value="json-object")
        assert result.audit.status is AgentExecutionStatus.DONE
        assert result.audit.execution_started is True
        assert result.audit.usage == {"prompt_tokens": 3, "completion_tokens": 2}
        assert result.audit.parse_mode == "json_object_client_validate"
        assert result.audit.output_hash is not None
        assert result.audit.trace_metadata["source"] == "unit"
        assert result.audit.trace_metadata["output_strategy"] == "json_object"
        assert result.audit.trace_metadata["schema_enforcement"] == "client_validate"
        assert len(llm_gateway.completions.calls) == 1
        assert llm_gateway.completions.calls[0]["model"] == "openai/local-json-object-model"
        assert llm_gateway.completions.calls[0]["base_url"] == "https://example.com/v1"
        assert llm_gateway.completions.calls[0]["timeout"] == 10.0

    asyncio.run(scenario())


def test_try_reserve_denies_when_runtime_full_and_releases_idempotently() -> None:
    async def scenario() -> None:
        gateway = _gateway()

        first = gateway.try_reserve()
        second = gateway.try_reserve()

        assert first.acquired is True
        assert second.acquired is False
        assert second.reason is AgentExecutionErrorClass.CAPACITY_DENIED

        await first.release()
        assert first.acquired is False
        await first.release()
        assert first.acquired is False
        third = gateway.try_reserve()
        assert third.acquired is True
        await third.release()

    asyncio.run(scenario())


def test_execute_uses_caller_reservation_without_double_acquiring_runtime_capacity() -> None:
    async def scenario() -> None:
        llm_gateway = FakeModelBackend()
        gateway = _gateway(llm_gateway=llm_gateway)
        reservation = gateway.try_reserve()

        try:
            result = await gateway.execute(_spec(), reservation=reservation)
            snapshot_while_reserved = gateway.status_snapshot()
            assert snapshot_while_reserved["in_flight"] == 1
        finally:
            await reservation.release()

        assert result.audit.status is AgentExecutionStatus.DONE
        assert len(llm_gateway.completions.calls) == 1
        snapshot_after_release = gateway.status_snapshot()
        assert snapshot_after_release["in_flight"] == 0

    asyncio.run(scenario())


def test_try_reserve_denies_rpm_before_provider_execution() -> None:
    async def scenario() -> None:
        gateway = _gateway(policy=_lane_rpm_policy())
        first = gateway.try_reserve()
        assert first.acquired is True
        await first.release()

        second = gateway.try_reserve()

        assert second.acquired is False
        assert second.reason is AgentExecutionErrorClass.RATE_LIMITED
        snapshot = gateway.status_snapshot()
        assert snapshot["in_flight"] == 0

    asyncio.run(scenario())


def test_try_reserve_rate_units_consume_multiple_rpm_slots_before_claim() -> None:
    async def scenario() -> None:
        policy = AgentRuntimePolicy(
            model="local-json-object-model",
            max_concurrency=2,
            rpm_limit=2,
            timeout_seconds=10,
        )
        gateway = _gateway(policy=policy)

        first = gateway.try_reserve(rate_units=2)
        assert first.acquired is True
        assert first.rate_units == 2
        snapshot = gateway.status_snapshot()
        assert snapshot["rpm_limit"] == 2
        await first.release()

        second = gateway.try_reserve()

        assert second.acquired is False
        assert second.reason is AgentExecutionErrorClass.RATE_LIMITED
        assert gateway.status_snapshot()["in_flight"] == 0

    asyncio.run(scenario())


def test_try_reserve_rejects_malformed_rate_units_before_capacity_claim() -> None:
    async def scenario() -> None:
        gateway = _gateway(policy=_lane_rpm_policy())

        for rate_units in (0, -1, True, "2"):
            with pytest.raises(ValueError, match="agent_execution_rate_units_required"):
                gateway.try_reserve(rate_units=rate_units)  # type: ignore[arg-type]

        snapshot = gateway.status_snapshot()
        assert snapshot["in_flight"] == 0

    asyncio.run(scenario())


def test_try_reserve_rate_units_clamps_batch_to_available_rpm_capacity() -> None:
    async def scenario() -> None:
        policy = AgentRuntimePolicy(
            model="local-json-object-model",
            max_concurrency=2,
            rpm_limit=2,
            timeout_seconds=10,
        )
        gateway = _gateway(policy=policy)

        reservation = gateway.try_reserve(rate_units=5)

        assert reservation.acquired is True
        assert reservation.rate_units == 2
        await reservation.release()

    asyncio.run(scenario())


def test_runtime_rpm_limit_applies_before_provider_execution() -> None:
    async def scenario() -> None:
        llm_gateway = FakeModelBackend()
        gateway = _gateway(llm_gateway=llm_gateway, policy=_lane_rpm_policy())

        first = await gateway.execute(_spec())
        assert first.audit.status is AgentExecutionStatus.DONE

        with pytest.raises(AgentExecutionError) as err:
            await gateway.execute(_spec())

        assert err.value.error_class is AgentExecutionErrorClass.RATE_LIMITED
        assert err.value.execution_started is False
        assert len(llm_gateway.completions.calls) == 1
        snapshot = gateway.status_snapshot()
        assert snapshot["in_flight"] == 0
        assert snapshot["rpm_limit"] == 1
        assert snapshot["provider_running"] == 0

    asyncio.run(scenario())


def test_execute_rejects_invalid_reservations_before_provider_call() -> None:
    async def scenario() -> None:
        llm_gateway = FakeModelBackend()
        gateway = _gateway(llm_gateway=llm_gateway)

        with pytest.raises(ValueError, match="acquired reservation"):
            await gateway.execute(
                _spec(),
                reservation=AgentCapacityReservation(
                    acquired=False,
                    reason=AgentExecutionErrorClass.CAPACITY_DENIED,
                ),
            )

        reservation = gateway.try_reserve()
        await reservation.release()
        with pytest.raises(ValueError, match="active acquired reservation"):
            await gateway.execute(_spec(), reservation=reservation)

        with pytest.raises(ValueError, match="not issued by this gateway"):
            await gateway.execute(_spec(), reservation=AgentCapacityReservation(acquired=True))

        assert llm_gateway.completions.calls == []

    asyncio.run(scenario())


def test_execute_rejects_other_gateway_reservation_before_provider_call() -> None:
    async def scenario() -> None:
        llm_gateway = FakeModelBackend()
        gateway = _gateway(llm_gateway=llm_gateway)
        other_gateway = _gateway()
        reservation = other_gateway.try_reserve()

        try:
            with pytest.raises(ValueError, match="not issued by this gateway"):
                await gateway.execute(_spec(), reservation=reservation)
        finally:
            await reservation.release()

        assert llm_gateway.completions.calls == []

    asyncio.run(scenario())


def test_execute_reuses_chat_client_for_same_stage_policy() -> None:
    async def scenario() -> None:
        llm_gateway = FakeModelBackend()
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
        llm_gateway = FakeModelBackend()
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
        llm_gateway = FakeModelBackend()
        gateway = _gateway(llm_gateway=llm_gateway, policy=_policy(failure_threshold=1))
        gateway.record_failure()

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
            llm_gateway=FakeModelBackend(completions=completions),
            policy=_policy(failure_threshold=1),
        )

        with pytest.raises(AgentExecutionError) as err:
            await gateway.execute(_spec())

        assert err.value.error_class is AgentExecutionErrorClass.QUOTA_EXHAUSTED
        assert err.value.execution_started is False
        assert len(completions.calls) == 1

        denied = gateway.try_reserve()
        assert denied.acquired is False
        assert denied.reason is AgentExecutionErrorClass.CIRCUIT_OPEN

    asyncio.run(scenario())


@pytest.mark.parametrize("message", ["quota unavailable", "payment failed"])
def test_quota_and_payment_provider_messages_are_quota_exhausted(message: str) -> None:
    async def scenario() -> None:
        completions = FakeJsonCompletions(exception=RuntimeError(message))
        gateway = _gateway(
            llm_gateway=FakeModelBackend(completions=completions),
            policy=_policy(failure_threshold=1),
        )

        with pytest.raises(AgentExecutionError) as err:
            await gateway.execute(_spec())

        assert err.value.error_class is AgentExecutionErrorClass.QUOTA_EXHAUSTED
        assert err.value.execution_started is False
        assert len(completions.calls) == 1

        denied = gateway.try_reserve()
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
            llm_gateway=FakeModelBackend(completions=completions),
            policy=_policy(failure_threshold=2),
        )

        with pytest.raises(AgentExecutionError) as err:
            await gateway.execute(_spec())

        assert err.value.error_class is expected_error_class
        assert err.value.execution_started is True
        assert len(completions.calls) == 1

        reservation = gateway.try_reserve()
        try:
            assert reservation.acquired is True
        finally:
            await reservation.release()

    asyncio.run(scenario())


def test_timeout_maps_to_execution_error_with_started_audit() -> None:
    async def scenario() -> None:
        completions = FakeJsonCompletions(delay_seconds=2)
        llm_gateway = FakeModelBackend(completions=completions)
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


def test_status_snapshot_is_flat_fixed_runtime_policy_and_counters() -> None:
    async def scenario() -> None:
        gateway = _gateway(policy=_policy(failure_threshold=1))

        reservation = gateway.try_reserve()
        denied = gateway.try_reserve()
        gateway.record_failure()
        snapshot = gateway.status_snapshot()

        assert reservation.acquired is True
        assert denied.reason is AgentExecutionErrorClass.CAPACITY_DENIED
        assert set(snapshot) == {
            "lane",
            "model",
            "provider_family",
            "output_strategy",
            "schema_enforcement",
            "max_concurrency",
            "rpm_limit",
            "timeout_seconds",
            "in_flight",
            "provider_running",
            "circuit_state",
            "circuit_open_until_ms",
            "capacity_denied_total",
            "circuit_open_total",
            "timeout_total",
            "last_denied_at_ms",
            "last_timeout_at_ms",
            "oldest_in_flight_age_ms",
        }
        assert snapshot["lane"] == AGENT_RUNTIME_LANE
        assert snapshot["max_concurrency"] == 1
        assert snapshot["timeout_seconds"] == 10.0
        assert snapshot["output_strategy"] == "json_object"
        assert snapshot["schema_enforcement"] == "client_validate"
        assert snapshot["in_flight"] == 1
        assert snapshot["circuit_state"] == "open"
        assert snapshot["capacity_denied_total"] == 1
        assert snapshot["circuit_open_total"] == 0
        assert snapshot["timeout_total"] == 0

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
        llm_gateway = FakeModelBackend(completions=FakeJsonCompletions(exception=exception))
        gateway = _gateway(llm_gateway=llm_gateway)

        if expected_error is None:
            await gateway.execute(_spec())
        else:
            with pytest.raises(expected_error):
                await gateway.execute(_spec())

        snapshot = gateway.status_snapshot()
        assert snapshot["in_flight"] == 0

    asyncio.run(scenario())


def test_execute_releases_internal_reservation_after_cancellation() -> None:
    async def scenario() -> None:
        entered = asyncio.Event()
        completions = FakeJsonCompletions(delay_seconds=60, entered=entered)
        gateway = _gateway(llm_gateway=FakeModelBackend(completions=completions))

        task = asyncio.create_task(gateway.execute(_spec()))
        await asyncio.wait_for(entered.wait(), timeout=1)
        task.cancel()
        with pytest.raises(AgentExecutionCancelled):
            await task

        snapshot = gateway.status_snapshot()
        assert snapshot["in_flight"] == 0

    asyncio.run(scenario())


def test_gateway_supervisor_cancellation_records_cancelled_audit_and_releases_reservation() -> None:
    async def scenario() -> None:
        entered = asyncio.Event()
        completions = FakeJsonCompletions(delay_seconds=60, entered=entered)
        gateway = _gateway(llm_gateway=FakeModelBackend(completions=completions))

        task = asyncio.create_task(gateway.execute(_spec()))
        await asyncio.wait_for(entered.wait(), timeout=1)
        running_snapshot = gateway.status_snapshot()
        assert running_snapshot["in_flight"] == 1
        assert running_snapshot["provider_running"] == 1

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
        assert snapshot["in_flight"] == 0
        assert snapshot["provider_running"] == 0

    asyncio.run(scenario())
