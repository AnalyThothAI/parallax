# Agent Model Capability Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** Draft
**Date:** 2026-05-20
**Owning spec:** Operator request: Phase 1 only, add model capability adapter for `deepseek-v4-flash` without domain coupling or compatibility branches.
**Worktree:** `.worktrees/agent-model-capability-adapter/`
**Branch:** `codex/agent-model-capability-adapter`

**Goal:** Add a first-class model capability adapter so lanes can run models with different structured-output capabilities, especially `deepseek-v4-flash` via official `json_object`, while keeping Pulse and other domains unaware of provider/model quirks.

**Architecture:** `AgentExecutionGateway` remains the single execution boundary. Domain clients still submit `AgentStageSpec` with instructions, input, and Pydantic output type; the gateway resolves a lane capability profile and delegates to one structured-output strategy. `json_schema` keeps the existing OpenAI Agents SDK path; `json_object` uses an OpenAI-compatible chat-completions strategy with client-side Pydantic validation and truthful audit metadata.

**Tech Stack:** Python 3.13, Pydantic v2, OpenAI Agents SDK, OpenAI-compatible chat completions, pytest, ruff, existing `AgentExecutionGateway` / `LLMGateway`.

---

## Scope

- In scope:
  - Add lane/model capability policy for structured output.
  - Add a strategy boundary under `integrations/openai_agents`.
  - Support `json_schema` and `json_object` as explicit strategies.
  - Make `deepseek-v4-flash` runnable only through a declared `json_object` capability profile.
  - Add unit, architecture, and opt-in live smoke tests.
  - Update worker config docs and audit contract docs.
- Out of scope:
  - No LiteLLM dependency, proxy, import, or config in this phase.
  - No fallback from failed `json_schema` to `json_object`.
  - No model-name checks inside `pulse_lab`, narrative, news, watchlist, social domains, or provider wiring.
  - No dual execution path in domain clients.
  - No compatibility aliases for old config names.
  - No durable DB schema migration unless an existing typed audit model requires a new persisted column. Prefer storing strategy metadata in existing audit JSON envelopes.

## Hard-Cut Rules

- [ ] Do not add `if model.startswith("deepseek")`, `if "qwen" in model`, or provider-specific branching outside the capability registry and strategy selection code.
- [ ] Do not modify `src/parallax/domains/pulse_lab/**` to know about DeepSeek, qwen, response formats, OpenAI SDK classes, or LiteLLM.
- [ ] Do not catch provider 400 errors and retry through a different output strategy. Strategy selection happens before the provider call.
- [ ] Do not use `drop_params`, silent parameter stripping, or best-effort compatibility behavior.
- [ ] Do not keep `parse_mode="strict"` for non-strict provider behavior. `json_object` must audit as client-validated JSON, not provider-enforced schema.
- [ ] Do not import `litellm` or add it to dependencies in this plan.
- [ ] Do not change queue/backpressure behavior except where tests need fake gateway metadata.

## Pre-flight

- [ ] Create an isolated worktree:

```bash
git worktree add .worktrees/agent-model-capability-adapter -b codex/agent-model-capability-adapter main
cd .worktrees/agent-model-capability-adapter
```

- [ ] Verify branch and clean status:

```bash
git branch --show-current
git status --short
```

Expected branch: `codex/agent-model-capability-adapter`; expected status: clean.

- [ ] Confirm runtime config paths before any live-data or live-LLM verification:

```bash
uv run parallax config
```

Expected: `config_path` and `workers_config_path` point at `~/.parallax/`. Do not print or copy secrets.

- [ ] Capture the current execution boundary:

```bash
rg -n "response_format|StrictJsonOutputSchema|Runner\\.run|Agent\\(|RunConfig\\(|deepseek|qwen|litellm" src tests
```

Expected before implementation: `StrictJsonOutputSchema` and SDK calls are concentrated in `integrations/openai_agents`; model strings appear in config defaults/tests only; `litellm` is absent.

- [ ] Run the baseline focused tests:

```bash
uv run pytest tests/unit/integrations/openai_agents/test_agent_execution_gateway.py tests/unit/integrations/openai_agents/test_agent_output_schema.py tests/unit/test_worker_settings.py tests/architecture/test_agent_execution_plane_contracts.py -q
```

Expected: pass in the worktree before edits. If local Postgres-backed integration tests are unavailable, record the environment gap and continue with unit/architecture tests.

---

## File Structure

### Create

- `src/parallax/platform/agent_capabilities.py`
  - Owns `AgentOutputStrategy`, `AgentSchemaEnforcement`, `AgentProviderFamily`, `AgentCapabilityProfile`, and profile resolution helpers.
  - This is the only platform file allowed to mention concrete model capability defaults such as `deepseek-v4-flash -> json_object`.

- `src/parallax/integrations/openai_agents/structured_output_strategy.py`
  - Owns the execution strategy protocol, shared execution context/outcome types, `AgentsJsonSchemaStrategy`, and `ChatJsonObjectStrategy`.
  - This is the only integration file allowed to set `response_format`.

- `tests/unit/test_agent_capabilities.py`
  - Tests profile defaults, explicit config overrides, and unsupported strategy rejection.

- `tests/unit/integrations/openai_agents/test_structured_output_strategy.py`
  - Tests `json_schema` strategy delegation and `json_object` chat request/parse/validation behavior with fake clients.

- `tests/architecture/test_agent_model_capability_contracts.py`
  - Guards against provider/model coupling leaking into domains or wiring.

- `tests/live/test_agent_model_capabilities_live.py`
  - Opt-in smoke tests skipped unless `GMGN_LIVE_LLM_SMOKE=1`.

### Modify

- `src/parallax/platform/agent_execution.py`
  - Add capability fields to `AgentLanePolicy`, `AgentRuntimeDefaultsPolicy`, `AgentExecutionRequestAudit`, and `AgentExecutionResultAudit`.
  - Add methods to resolve a lane's capability profile without importing integration code.

- `src/parallax/platform/config/settings.py`
  - Add worker YAML fields for capability policy.
  - Keep defaults compatible with the current qwen path by defaulting to `json_schema`.
  - Accept explicit lane override for `deepseek-v4-flash` using `json_object`.

- `src/parallax/integrations/openai_agents/agent_execution_gateway.py`
  - Replace in-method structured-output construction with strategy selection.
  - Preserve reservation, rate-limit, timeout, circuit breaker, telemetry, and audit behavior.

- `src/parallax/integrations/openai_agents/agent_output_schema.py`
  - Keep current strict schema wrapper for `json_schema`.
  - Expose schema name/hash helpers if needed by `ChatJsonObjectStrategy`; do not add provider-specific logic here.

- `src/parallax/app/runtime/provider_wiring/openai.py`
  - Pass policy through as today. Do not add model/provider if branches.

- `docs/CONTRACTS.md`
  - Document `agent_runtime` capability fields and audit semantics.

- `docs/WORKERS.md`
  - Document example lane configuration for `deepseek-v4-flash`.

- `docs/ARCHITECTURE.md`
  - Document that model capability adaptation belongs to the execution plane, not domains.

---

## Target Config Shape

Default qwen-like lanes keep provider-enforced schema:

```yaml
agent_runtime:
  defaults:
    model: qwen3.6
    output_strategy: json_schema
    schema_enforcement: provider
```

DeepSeek lane override uses official JSON output:

```yaml
agent_runtime:
  lanes:
    pulse.signal_analyst:
      model: deepseek-v4-flash
      output_strategy: json_object
      schema_enforcement: client_validate
```

If `model: deepseek-v4-flash` is set without explicit capability fields, the central capability registry may resolve the same `json_object/client_validate` profile. Tests must still prove this resolution happens in one place only.

---

## Task 1 - Lock Capability Contract With Failing Tests

**Files:**

- Create: `tests/unit/test_agent_capabilities.py`
- Modify: `tests/unit/test_worker_settings.py`
- Create: `tests/architecture/test_agent_model_capability_contracts.py`

- [ ] **Step 1: Add capability model tests**

Create `tests/unit/test_agent_capabilities.py`:

```python
from __future__ import annotations

import pytest

from parallax.platform.agent_capabilities import (
    AgentCapabilityProfile,
    AgentOutputStrategy,
    AgentProviderFamily,
    AgentSchemaEnforcement,
    capability_profile_for,
)


def test_default_profile_uses_provider_enforced_json_schema() -> None:
    profile = capability_profile_for(model="qwen3.6")

    assert profile.provider_family == AgentProviderFamily.OPENAI_COMPATIBLE
    assert profile.output_strategy == AgentOutputStrategy.JSON_SCHEMA
    assert profile.schema_enforcement == AgentSchemaEnforcement.PROVIDER


def test_deepseek_v4_flash_profile_uses_json_object_client_validation() -> None:
    profile = capability_profile_for(model="deepseek-v4-flash")

    assert profile.provider_family == AgentProviderFamily.DEEPSEEK
    assert profile.output_strategy == AgentOutputStrategy.JSON_OBJECT
    assert profile.schema_enforcement == AgentSchemaEnforcement.CLIENT_VALIDATE


def test_explicit_profile_overrides_model_default_without_model_branching() -> None:
    profile = capability_profile_for(
        model="any-openai-compatible-model",
        explicit=AgentCapabilityProfile(
            provider_family=AgentProviderFamily.OPENAI_COMPATIBLE,
            output_strategy=AgentOutputStrategy.JSON_OBJECT,
            schema_enforcement=AgentSchemaEnforcement.CLIENT_VALIDATE,
        ),
    )

    assert profile.output_strategy == AgentOutputStrategy.JSON_OBJECT
    assert profile.schema_enforcement == AgentSchemaEnforcement.CLIENT_VALIDATE


def test_client_validate_requires_json_object_strategy() -> None:
    with pytest.raises(ValueError, match="client_validate"):
        AgentCapabilityProfile(
            provider_family=AgentProviderFamily.OPENAI_COMPATIBLE,
            output_strategy=AgentOutputStrategy.JSON_SCHEMA,
            schema_enforcement=AgentSchemaEnforcement.CLIENT_VALIDATE,
        )
```

Expected before implementation: import failure for `platform.agent_capabilities`.

- [ ] **Step 2: Add worker settings tests for capability fields**

Append to `tests/unit/test_worker_settings.py`:

```python
def test_agent_runtime_lane_accepts_explicit_output_strategy() -> None:
    settings = WorkersSettings(
        agent_runtime={
            "lanes": {
                "pulse.signal_analyst": {
                    "model": "deepseek-v4-flash",
                    "output_strategy": "json_object",
                    "schema_enforcement": "client_validate",
                    "provider_family": "deepseek",
                }
            }
        }
    )

    lane = settings.agent_runtime.lanes["pulse.signal_analyst"]
    assert lane.model == "deepseek-v4-flash"
    assert lane.output_strategy == "json_object"
    assert lane.schema_enforcement == "client_validate"
    assert lane.provider_family == "deepseek"


def test_agent_runtime_defaults_keep_json_schema_contract() -> None:
    settings = WorkersSettings()

    assert settings.agent_runtime.defaults.output_strategy == "json_schema"
    assert settings.agent_runtime.defaults.schema_enforcement == "provider"
    assert settings.agent_runtime.defaults.provider_family == "openai_compatible"


def test_agent_runtime_rejects_unknown_output_strategy() -> None:
    with pytest.raises(ValidationError):
        WorkersSettings(agent_runtime={"defaults": {"output_strategy": "best_effort_json"}})
```

Expected before implementation: validation errors because fields are currently forbidden.

- [ ] **Step 3: Add architecture leakage tests**

Create `tests/architecture/test_agent_model_capability_contracts.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "parallax"

pytestmark = pytest.mark.architecture

ALLOWED_MODEL_CAPABILITY_FILES = {
    SRC / "platform" / "agent_capabilities.py",
}

ALLOWED_RESPONSE_FORMAT_FILES = {
    SRC / "integrations" / "openai_agents" / "structured_output_strategy.py",
}


def _py_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.py") if "__pycache__" not in path.parts)


def test_provider_model_names_do_not_leak_into_domains_or_wiring() -> None:
    forbidden_tokens = ("deepseek", "qwen")
    violations: list[str] = []
    checked_roots = [
        SRC / "domains",
        SRC / "app" / "runtime" / "provider_wiring",
        SRC / "integrations" / "openai_agents",
    ]
    for root in checked_roots:
        for path in _py_files(root):
            if path in ALLOWED_MODEL_CAPABILITY_FILES:
                continue
            text = path.read_text(encoding="utf-8").lower()
            for token in forbidden_tokens:
                if token in text and "test" not in path.parts:
                    violations.append(f"{path.relative_to(ROOT)} contains {token}")

    assert violations == []


def test_response_format_is_owned_by_structured_output_strategy_only() -> None:
    violations: list[str] = []
    for path in _py_files(SRC):
        if path in ALLOWED_RESPONSE_FORMAT_FILES:
            continue
        text = path.read_text(encoding="utf-8")
        if "response_format" in text:
            violations.append(str(path.relative_to(ROOT)))

    assert violations == []


def test_litellm_is_not_introduced_in_phase_one() -> None:
    violations: list[str] = []
    for path in _py_files(SRC):
        if "litellm" in path.read_text(encoding="utf-8").lower():
            violations.append(str(path.relative_to(ROOT)))

    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8").lower()
    assert violations == []
    assert "litellm" not in pyproject
```

Before implementation this may need one allowlist adjustment for existing comments/tests that mention qwen in `agent_output_schema.py` and `test_pulse_decision_agent_client.py`. Do not widen the allowlist to domains; instead update comments to describe capability behavior without provider names.

- [ ] **Step 4: Run red tests**

```bash
uv run pytest tests/unit/test_agent_capabilities.py tests/unit/test_worker_settings.py tests/architecture/test_agent_model_capability_contracts.py -q
```

Expected: fail only because the new capability contract is not implemented yet.

---

## Task 2 - Add Platform Capability Types

**Files:**

- Create: `src/parallax/platform/agent_capabilities.py`
- Modify: `src/parallax/platform/agent_execution.py`

- [ ] **Step 1: Implement capability profile types**

Create `src/parallax/platform/agent_capabilities.py`:

```python
from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class AgentOutputStrategy(StrEnum):
    JSON_SCHEMA = "json_schema"
    JSON_OBJECT = "json_object"


class AgentSchemaEnforcement(StrEnum):
    PROVIDER = "provider"
    CLIENT_VALIDATE = "client_validate"


class AgentProviderFamily(StrEnum):
    OPENAI_COMPATIBLE = "openai_compatible"
    DEEPSEEK = "deepseek"


class AgentCapabilityProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_family: AgentProviderFamily = AgentProviderFamily.OPENAI_COMPATIBLE
    output_strategy: AgentOutputStrategy = AgentOutputStrategy.JSON_SCHEMA
    schema_enforcement: AgentSchemaEnforcement = AgentSchemaEnforcement.PROVIDER
    client_validation_retries: int = 1

    @field_validator("client_validation_retries", mode="before")
    @classmethod
    def parse_client_validation_retries(cls, value: Any) -> int:
        return max(0, int(value or 0))

    @model_validator(mode="after")
    def validate_enforcement(self) -> "AgentCapabilityProfile":
        if self.output_strategy == AgentOutputStrategy.JSON_SCHEMA:
            if self.schema_enforcement != AgentSchemaEnforcement.PROVIDER:
                raise ValueError("json_schema output_strategy requires provider schema_enforcement")
        if self.output_strategy == AgentOutputStrategy.JSON_OBJECT:
            if self.schema_enforcement != AgentSchemaEnforcement.CLIENT_VALIDATE:
                raise ValueError("json_object output_strategy requires client_validate schema_enforcement")
        return self


_MODEL_CAPABILITY_DEFAULTS: dict[str, AgentCapabilityProfile] = {
    "deepseek-v4-flash": AgentCapabilityProfile(
        provider_family=AgentProviderFamily.DEEPSEEK,
        output_strategy=AgentOutputStrategy.JSON_OBJECT,
        schema_enforcement=AgentSchemaEnforcement.CLIENT_VALIDATE,
        client_validation_retries=1,
    ),
}


def capability_profile_for(
    *,
    model: str,
    explicit: AgentCapabilityProfile | None = None,
) -> AgentCapabilityProfile:
    if explicit is not None:
        return explicit
    key = str(model or "").strip().lower()
    profile = _MODEL_CAPABILITY_DEFAULTS.get(key)
    if profile is not None:
        return profile
    return AgentCapabilityProfile()


__all__ = [
    "AgentCapabilityProfile",
    "AgentOutputStrategy",
    "AgentProviderFamily",
    "AgentSchemaEnforcement",
    "capability_profile_for",
]
```

- [ ] **Step 2: Add capability fields to runtime policy**

In `src/parallax/platform/agent_execution.py`, import the capability types and extend `AgentLanePolicy` plus `AgentRuntimeDefaultsPolicy`:

```python
from parallax.platform.agent_capabilities import (
    AgentCapabilityProfile,
    AgentOutputStrategy,
    AgentProviderFamily,
    AgentSchemaEnforcement,
    capability_profile_for,
)
```

Add fields:

```python
provider_family: AgentProviderFamily | None = None
output_strategy: AgentOutputStrategy | None = None
schema_enforcement: AgentSchemaEnforcement | None = None
client_validation_retries: int | None = Field(default=None, ge=0)
```

Add to defaults with non-optional values:

```python
provider_family: AgentProviderFamily = AgentProviderFamily.OPENAI_COMPATIBLE
output_strategy: AgentOutputStrategy = AgentOutputStrategy.JSON_SCHEMA
schema_enforcement: AgentSchemaEnforcement = AgentSchemaEnforcement.PROVIDER
client_validation_retries: int = Field(default=1, ge=0)
```

- [ ] **Step 3: Add lane capability resolution**

Add to `AgentRuntimePolicy`:

```python
def capability_for_lane(self, lane: str) -> AgentCapabilityProfile:
    lane_policy = self.lane_for(lane)
    explicit = None
    if (
        lane_policy.provider_family is not None
        or lane_policy.output_strategy is not None
        or lane_policy.schema_enforcement is not None
        or lane_policy.client_validation_retries is not None
    ):
        explicit = AgentCapabilityProfile(
            provider_family=lane_policy.provider_family or self.defaults.provider_family,
            output_strategy=lane_policy.output_strategy or self.defaults.output_strategy,
            schema_enforcement=lane_policy.schema_enforcement or self.defaults.schema_enforcement,
            client_validation_retries=(
                lane_policy.client_validation_retries
                if lane_policy.client_validation_retries is not None
                else self.defaults.client_validation_retries
            ),
        )
    return capability_profile_for(model=self.model_for_lane(lane), explicit=explicit)
```

- [ ] **Step 4: Add audit capability fields**

Extend `AgentExecutionRequestAudit`:

```python
provider_family: str = "openai_compatible"
output_strategy: str = "json_schema"
schema_enforcement: str = "provider"
```

Update `from_stage(...)` signature to accept `capability_profile: AgentCapabilityProfile`, then include:

```python
"provider_family": capability_profile.provider_family.value,
"output_strategy": capability_profile.output_strategy.value,
"schema_enforcement": capability_profile.schema_enforcement.value,
```

in both model fields and `trace_metadata`.

- [ ] **Step 5: Run policy tests**

```bash
uv run pytest tests/unit/test_agent_capabilities.py tests/unit/integrations/openai_agents/test_agent_execution_audit.py -q
```

Expected: pass after updating audit tests to assert the default `json_schema/provider` metadata.

---

## Task 3 - Add Worker Config Fields Without Legacy Aliases

**Files:**

- Modify: `src/parallax/platform/config/settings.py`
- Modify: `tests/unit/test_worker_settings.py`

- [ ] **Step 1: Add config fields to settings models**

In `AgentLaneSettings`, add:

```python
provider_family: Literal["openai_compatible", "deepseek"] | None = None
output_strategy: Literal["json_schema", "json_object"] | None = None
schema_enforcement: Literal["provider", "client_validate"] | None = None
client_validation_retries: int | None = Field(default=None, ge=0)
```

In `AgentRuntimeDefaultsSettings`, add:

```python
provider_family: Literal["openai_compatible", "deepseek"] = "openai_compatible"
output_strategy: Literal["json_schema", "json_object"] = "json_schema"
schema_enforcement: Literal["provider", "client_validate"] = "provider"
client_validation_retries: int = Field(default=1, ge=0)
```

- [ ] **Step 2: Add validators for impossible combinations**

Add a small local function in `settings.py`:

```python
def _validate_agent_capability_pair(output_strategy: str | None, schema_enforcement: str | None) -> None:
    if output_strategy == "json_schema" and schema_enforcement not in {None, "provider"}:
        raise ValueError("json_schema output_strategy requires provider schema_enforcement")
    if output_strategy == "json_object" and schema_enforcement not in {None, "client_validate"}:
        raise ValueError("json_object output_strategy requires client_validate schema_enforcement")
```

Call it from `AgentLaneSettings` and `AgentRuntimeDefaultsSettings` model validators.

- [ ] **Step 3: Update default workers YAML**

In `default_workers_yaml()`, add under `agent_runtime.defaults`:

```yaml
    provider_family: openai_compatible
    output_strategy: json_schema
    schema_enforcement: provider
    client_validation_retries: 1
```

Do not add DeepSeek defaults to the YAML example except in docs. The repo default remains the current qwen-like provider-enforced schema path.

- [ ] **Step 4: Run config tests**

```bash
uv run pytest tests/unit/test_worker_settings.py tests/unit/test_provider_wiring_agent_execution_gateway.py -q
```

Expected: pass with default gateway policy carrying `json_schema/provider` and explicit DeepSeek lane overrides accepted.

---

## Task 4 - Extract Structured Output Strategies

**Files:**

- Create: `src/parallax/integrations/openai_agents/structured_output_strategy.py`
- Modify: `src/parallax/integrations/openai_agents/agent_execution_gateway.py`
- Create: `tests/unit/integrations/openai_agents/test_structured_output_strategy.py`
- Modify: `tests/unit/integrations/openai_agents/test_agent_execution_gateway.py`

- [ ] **Step 1: Write fake client tests for json_object**

Create `tests/unit/integrations/openai_agents/test_structured_output_strategy.py` with fake OpenAI response objects:

```python
from __future__ import annotations

import asyncio
from typing import Any

import pytest
from pydantic import BaseModel

from parallax.integrations.openai_agents.structured_output_strategy import (
    ChatJsonObjectStrategy,
    StructuredOutputContext,
)
from parallax.platform.agent_capabilities import (
    AgentCapabilityProfile,
    AgentOutputStrategy,
    AgentProviderFamily,
    AgentSchemaEnforcement,
)
from parallax.platform.agent_execution import AgentRuntimeDefaultsPolicy, AgentStageSpec


class Payload(BaseModel):
    value: str


class FakeMessage:
    content = '{"value":"ok"}'


class FakeChoice:
    message = FakeMessage()


class FakeResponse:
    choices = [FakeChoice()]
    usage = {"prompt_tokens": 8, "completion_tokens": 4}


class FakeCompletions:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> FakeResponse:
        self.calls.append(kwargs)
        return FakeResponse()


class FakeChat:
    def __init__(self) -> None:
        self.completions = FakeCompletions()


class FakeClient:
    def __init__(self) -> None:
        self.chat = FakeChat()


def _stage() -> AgentStageSpec:
    return AgentStageSpec(
        lane="pulse.signal_analyst",
        stage="signal_analyst",
        instructions="Return JSON for the signal.",
        input_payload={"token": "ABC"},
        output_type=Payload,
        prompt_version="p1",
        schema_version="s1",
        workflow_name="workflow",
        agent_name="agent",
    )


def test_json_object_strategy_uses_official_response_format_and_client_validation() -> None:
    async def scenario() -> None:
        client = FakeClient()
        strategy = ChatJsonObjectStrategy(openai_client_factory=lambda **_: client)
        outcome = await strategy.run(
            StructuredOutputContext(
                stage=_stage(),
                model_name="deepseek-v4-flash",
                timeout_seconds=30.0,
                defaults=AgentRuntimeDefaultsPolicy(model="qwen3.6"),
                capability_profile=AgentCapabilityProfile(
                    provider_family=AgentProviderFamily.DEEPSEEK,
                    output_strategy=AgentOutputStrategy.JSON_OBJECT,
                    schema_enforcement=AgentSchemaEnforcement.CLIENT_VALIDATE,
                ),
                trace_metadata={},
            )
        )

        call = client.chat.completions.calls[0]
        assert call["model"] == "deepseek-v4-flash"
        assert call["response_format"] == {"type": "json_object"}
        assert "tools" not in call
        assert "tool_choice" not in call
        assert "json" in call["messages"][0]["content"].lower()
        assert '"value"' in call["messages"][0]["content"]
        assert outcome.final_output == Payload(value="ok")
        assert outcome.audit_extra["parse_mode"] == "json_object_client_validate"
        assert outcome.audit_extra["schema_enforcement"] == "client_validate"

    asyncio.run(scenario())
```

- [ ] **Step 2: Implement shared context/outcome types**

Add to `structured_output_strategy.py`:

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from agents import Agent, RunConfig, Runner
from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
from pydantic import ValidationError

from parallax.integrations.openai_agents.agent_model_settings import default_agent_model_settings
from parallax.integrations.openai_agents.agent_output_schema import StrictJsonOutputSchema
from parallax.integrations.openai_agents.instructor_safety_net import (
    InstructorSafetyNet,
    extract_sdk_usage,
)
from parallax.platform.agent_capabilities import AgentCapabilityProfile
from parallax.platform.agent_execution import AgentRuntimeDefaultsPolicy, AgentStageSpec


@dataclass(frozen=True, slots=True)
class StructuredOutputContext:
    stage: AgentStageSpec
    model_name: str
    timeout_seconds: float
    defaults: AgentRuntimeDefaultsPolicy
    capability_profile: AgentCapabilityProfile
    trace_metadata: dict[str, Any]
    trace_id: str = ""
    group_id: str = ""
    trace_enabled: bool = False
    trace_include_sensitive_data: bool = False


@dataclass(frozen=True, slots=True)
class StructuredOutputOutcome:
    final_output: Any
    raw_result: Any | None
    audit_extra: dict[str, Any]


class StructuredOutputStrategy(Protocol):
    async def run(self, context: StructuredOutputContext) -> StructuredOutputOutcome:
        ...
```

- [ ] **Step 3: Move current Agents SDK path into `AgentsJsonSchemaStrategy`**

Add class:

```python
class AgentsJsonSchemaStrategy:
    def __init__(
        self,
        *,
        model_factory: Callable[[str, float], Any],
        runner: Any | None = None,
        safety_net: InstructorSafetyNet | None = None,
    ) -> None:
        self._model_factory = model_factory
        self._runner = runner or Runner
        self._safety_net = safety_net

    async def run(self, context: StructuredOutputContext) -> StructuredOutputOutcome:
        output_schema = StrictJsonOutputSchema(context.stage.output_type)
        model = self._model_factory(context.model_name, context.timeout_seconds)
        agent = Agent(
            name=context.stage.agent_name,
            instructions=context.stage.instructions,
            output_type=output_schema,
            tools=context.stage.tools,
            model=model,
            model_settings=default_agent_model_settings(
                disable_thinking=context.defaults.disable_thinking,
                include_usage=context.defaults.include_usage,
            ),
        )
        run_config = RunConfig(
            workflow_name=context.stage.workflow_name,
            trace_id=context.trace_id,
            group_id=context.group_id,
            trace_include_sensitive_data=context.trace_include_sensitive_data,
            tracing_disabled=not context.trace_enabled,
            trace_metadata=context.trace_metadata,
        )
        runner_input = _runner_input_payload(context.stage.input_payload)
        if self._safety_net is not None:
            final_output, audit_extra, raw_result = await self._safety_net.run_with_safety_net(
                agent=agent,
                input_payload=runner_input,
                run_config=run_config,
                pydantic_output_type=getattr(output_schema, "output_type", context.stage.output_type),
                context=None,
                max_turns=context.stage.max_turns,
                return_result=True,
            )
            return StructuredOutputOutcome(final_output, raw_result, dict(audit_extra))
        raw_result = await self._runner.run(
            agent,
            runner_input,
            max_turns=context.stage.max_turns,
            run_config=run_config,
        )
        return StructuredOutputOutcome(
            getattr(raw_result, "final_output", None),
            raw_result,
            {
                "safety_net_used": False,
                "safety_net_retries": 0,
                "parse_mode": "strict_json_schema",
                "usage": extract_sdk_usage(raw_result),
            },
        )
```

Move `_runner_input_payload` from `agent_execution_gateway.py` into this module or import it from one place. Do not duplicate it.

- [ ] **Step 4: Implement `ChatJsonObjectStrategy`**

Add:

```python
class ChatJsonObjectStrategy:
    def __init__(self, *, openai_client_factory: Callable[..., Any]) -> None:
        self._openai_client_factory = openai_client_factory

    async def run(self, context: StructuredOutputContext) -> StructuredOutputOutcome:
        if context.stage.max_turns != 1:
            raise ValueError("json_object strategy supports max_turns=1 only")
        schema = StrictJsonOutputSchema(context.stage.output_type).json_schema()
        client = self._openai_client_factory(
            model=context.model_name,
            timeout_s=context.timeout_seconds,
        )
        messages = _json_object_messages(
            instructions=context.stage.instructions,
            input_payload=context.stage.input_payload,
            schema=schema,
        )
        attempts = max(1, int(context.capability_profile.client_validation_retries) + 1)
        last_error: Exception | None = None
        raw_response: Any | None = None
        for attempt_index in range(attempts):
            raw_response = await client.chat.completions.create(
                model=context.model_name,
                messages=messages,
                response_format={"type": "json_object"},
            )
            text = _first_message_content(raw_response)
            try:
                parsed = StrictJsonOutputSchema(context.stage.output_type).validate_json(text)
                return StructuredOutputOutcome(
                    parsed,
                    raw_response,
                    {
                        "safety_net_used": attempt_index > 0,
                        "safety_net_retries": attempt_index,
                        "parse_mode": "json_object_client_validate",
                        "schema_enforcement": "client_validate",
                        "usage": extract_sdk_usage(raw_response),
                    },
                )
            except ValidationError as exc:
                last_error = exc
                messages = _append_validation_reask(messages, error=str(exc), schema=schema)
        raise last_error or ValueError("json_object response validation failed")
```

Add helper functions:

```python
def _json_object_messages(*, instructions: str, input_payload: Any, schema: dict[str, Any]) -> list[dict[str, str]]:
    system = (
        f"{instructions.strip()}\n\n"
        "Return exactly one valid JSON object. Do not include markdown. "
        "The JSON object must match this JSON schema after application-side validation:\n"
        f"{json.dumps(schema, ensure_ascii=False, sort_keys=True)}"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(input_payload, ensure_ascii=False, sort_keys=True)},
    ]


def _first_message_content(response: Any) -> str:
    choices = getattr(response, "choices", None) or []
    if not choices:
        return ""
    message = getattr(choices[0], "message", None)
    content = getattr(message, "content", None)
    return str(content or "")


def _append_validation_reask(
    messages: list[dict[str, str]],
    *,
    error: str,
    schema: dict[str, Any],
) -> list[dict[str, str]]:
    return [
        *messages,
        {
            "role": "user",
            "content": (
                "The previous JSON object failed application validation. "
                f"Validation error: {error[:1000]}\n"
                "Return one corrected JSON object only for this schema:\n"
                f"{json.dumps(schema, ensure_ascii=False, sort_keys=True)}"
            ),
        },
    ]
```

This retry is not a strategy fallback. It stays inside `json_object` and only handles malformed or schema-invalid JSON.

- [ ] **Step 5: Wire strategies into gateway**

In `AgentExecutionGateway.__init__`, initialize:

```python
self._chat_client_cache: dict[tuple[str, str, float], Any] = {}
self._json_schema_strategy = AgentsJsonSchemaStrategy(
    model_factory=lambda model_name, timeout_s: self._model_for(model_name, timeout_s=timeout_s),
    runner=self._runner,
    safety_net=self._safety_net,
)
self._json_object_strategy = ChatJsonObjectStrategy(
    openai_client_factory=lambda model, timeout_s: self._chat_client_for(
        model=model,
        timeout_s=timeout_s,
    ),
)
```

Add a gateway-local chat client cache next to `_model_for`:

```python
def _chat_client_for(self, *, model: str, timeout_s: float) -> Any:
    key = (str(model), self._base_url, float(timeout_s))
    cached = self._chat_client_cache.get(key)
    if cached is not None:
        return cached
    client = self._llm_gateway.openai_client(
        model=model,
        base_url=self._base_url,
        timeout_s=float(timeout_s),
    )
    self._chat_client_cache[key] = client
    return client
```

Add:

```python
def _strategy_for(self, profile: AgentCapabilityProfile) -> StructuredOutputStrategy:
    if profile.output_strategy == AgentOutputStrategy.JSON_SCHEMA:
        return self._json_schema_strategy
    if profile.output_strategy == AgentOutputStrategy.JSON_OBJECT:
        return self._json_object_strategy
    raise ValueError(f"unsupported agent output strategy: {profile.output_strategy}")
```

Change `_run_stage()` to build `StructuredOutputContext` and call the selected strategy. Keep `runner_entered["value"] = True` immediately before strategy invocation so provider-started audit semantics remain true.

- [ ] **Step 6: Run strategy and gateway tests**

```bash
uv run pytest tests/unit/integrations/openai_agents/test_structured_output_strategy.py tests/unit/integrations/openai_agents/test_agent_execution_gateway.py -q
```

Expected: pass. Existing json_schema gateway behavior remains unchanged except `parse_mode` value becomes `strict_json_schema`; update assertions accordingly.

---

## Task 5 - Make Audit And Artifact Hash Capability-Aware

**Files:**

- Modify: `src/parallax/integrations/openai_agents/agent_execution_gateway.py`
- Modify: `src/parallax/platform/agent_execution.py`
- Modify: `tests/unit/integrations/openai_agents/test_agent_execution_audit.py`
- Modify: `tests/unit/test_pulse_decision_agent_client.py`
- Modify: `tests/unit/integrations/openai_agents/test_news_item_brief_agent_client.py`

- [ ] **Step 1: Include capability profile in request audit**

In `AgentExecutionGateway.request_audit(stage)`, compute:

```python
model_name = self.model_for_lane(stage.lane)
capability_profile = self._policy.capability_for_lane(stage.lane)
```

Include these fields in `artifact_hash_for(...)` source:

```python
output_strategy=capability_profile.output_strategy.value,
schema_enforcement=capability_profile.schema_enforcement.value,
provider_family=capability_profile.provider_family.value,
```

Then pass `capability_profile` into `AgentExecutionRequestAudit.from_stage(...)`.

- [ ] **Step 2: Surface strategy fields in status snapshot**

Add to each lane status:

```python
"provider_family": capability_profile.provider_family.value,
"output_strategy": capability_profile.output_strategy.value,
"schema_enforcement": capability_profile.schema_enforcement.value,
```

Do not include prompts, schemas, input payloads, API keys, or raw provider responses in status.

- [ ] **Step 3: Add audit tests**

In `tests/unit/integrations/openai_agents/test_agent_execution_audit.py`, add:

```python
def test_request_audit_includes_capability_profile_and_hash_changes() -> None:
    json_schema_gateway = _gateway_with_policy(
        AgentRuntimePolicy(
            defaults=AgentRuntimeDefaultsPolicy(model="qwen3.6"),
            lanes={"test.lane": AgentLanePolicy(timeout_seconds=10)},
        )
    )
    json_object_gateway = _gateway_with_policy(
        AgentRuntimePolicy(
            defaults=AgentRuntimeDefaultsPolicy(model="qwen3.6"),
            lanes={
                "test.lane": AgentLanePolicy(
                    model="deepseek-v4-flash",
                    output_strategy="json_object",
                    schema_enforcement="client_validate",
                    provider_family="deepseek",
                    timeout_seconds=10,
                )
            },
        )
    )

    strict_audit = json_schema_gateway.request_audit(_spec())
    object_audit = json_object_gateway.request_audit(_spec())

    assert strict_audit.output_strategy == "json_schema"
    assert strict_audit.schema_enforcement == "provider"
    assert object_audit.output_strategy == "json_object"
    assert object_audit.schema_enforcement == "client_validate"
    assert strict_audit.artifact_version_hash != object_audit.artifact_version_hash
```

- [ ] **Step 4: Keep Pulse audit domain-owned**

Update Pulse and News tests only where they assert exact `parse_mode` or artifact hash values. Do not add provider/model branches to Pulse code.

- [ ] **Step 5: Run audit-facing tests**

```bash
uv run pytest tests/unit/integrations/openai_agents/test_agent_execution_audit.py tests/unit/test_pulse_decision_agent_client.py tests/unit/integrations/openai_agents/test_news_item_brief_agent_client.py -q
```

Expected: pass with strategy metadata present in execution audit and flowing into existing domain audit JSON.

---

## Task 6 - Prove Pulse Has No Model Coupling

**Files:**

- Modify: `tests/architecture/test_agent_model_capability_contracts.py`
- Modify: `tests/unit/test_pulse_decision_agent_client.py`
- Modify: `tests/unit/test_pulse_candidate_worker.py` only if fake gateway snapshots need new metadata.

- [ ] **Step 1: Tighten architecture allowlists**

After implementation, adjust `test_provider_model_names_do_not_leak_into_domains_or_wiring()` so concrete model/provider capability tokens are allowed only in:

```python
ALLOWED_MODEL_CAPABILITY_FILES = {
    SRC / "platform" / "agent_capabilities.py",
    SRC / "platform" / "config" / "settings.py",
}
```

Do not allow `src/parallax/domains/pulse_lab/**`.

- [ ] **Step 2: Add Pulse client test with json_object lane policy**

In `tests/unit/test_pulse_decision_agent_client.py`, add a fake gateway whose `execute()` returns valid stage Pydantic objects and whose audit contains:

```python
AgentExecutionResultAudit(
    provider_family="deepseek",
    output_strategy="json_object",
    schema_enforcement="client_validate",
    parse_mode="json_object_client_validate",
    ...
)
```

Assert:

```python
assert result.stage_audits[0].parse_mode == "json_object_client_validate"
assert result.stage_audits[0].trace_metadata_json["output_strategy"] == "json_object"
assert "deepseek" not in OpenAIAgentsPulseDecisionClient.__module__
```

If the last assertion is too weak, rely on the architecture test instead.

- [ ] **Step 3: Run Pulse-focused tests**

```bash
uv run pytest tests/unit/test_pulse_decision_agent_client.py tests/unit/test_pulse_candidate_worker.py tests/architecture/test_agent_model_capability_contracts.py -q
```

Expected: pass. No Pulse production file contains `deepseek`, `qwen`, `json_object`, `json_schema`, `response_format`, or `litellm`.

---

## Task 7 - Add Opt-In Live Smoke Tests

**Files:**

- Create: `tests/live/test_agent_model_capabilities_live.py`
- Modify: `pyproject.toml` only if a `live` pytest marker is not already declared.

- [ ] **Step 1: Add skipped-by-default live tests**

Create `tests/live/test_agent_model_capabilities_live.py`:

```python
from __future__ import annotations

import os

import pytest
from pydantic import BaseModel

from parallax.app.runtime.llm_gateway import LLMGateway
from parallax.integrations.openai_agents.agent_execution_gateway import AgentExecutionGateway
from parallax.platform.agent_execution import (
    AgentLanePolicy,
    AgentRuntimeDefaultsPolicy,
    AgentRuntimePolicy,
    AgentStageSpec,
)
from parallax.platform.config.settings import load_settings


pytestmark = pytest.mark.live


class ProbePayload(BaseModel):
    ok: bool
    label: str


def _skip_unless_enabled() -> None:
    if os.environ.get("GMGN_LIVE_LLM_SMOKE") != "1":
        pytest.skip("set GMGN_LIVE_LLM_SMOKE=1 to run live LLM smoke tests")


def _stage(lane: str) -> AgentStageSpec:
    return AgentStageSpec(
        lane=lane,
        stage="probe",
        instructions="Return JSON with ok=true and label='probe'.",
        input_payload={"label": "probe"},
        output_type=ProbePayload,
        prompt_version="probe-v1",
        schema_version="probe-v1",
        workflow_name="parallax.probe",
        agent_name="ProbeAgent",
    )


@pytest.mark.asyncio
async def test_live_deepseek_v4_flash_json_object_strategy() -> None:
    _skip_unless_enabled()
    settings = load_settings(require_ws_token=False)
    llm_gateway = LLMGateway.create(settings)
    gateway = AgentExecutionGateway(
        llm_gateway=llm_gateway,
        base_url=settings.llm_base_url,
        trace_enabled=False,
        trace_include_sensitive_data=False,
        policy=AgentRuntimePolicy(
            defaults=AgentRuntimeDefaultsPolicy(model="qwen3.6"),
            global_max_concurrency=1,
            global_rpm_limit=60,
            lanes={
                "probe.deepseek": AgentLanePolicy(
                    model="deepseek-v4-flash",
                    provider_family="deepseek",
                    output_strategy="json_object",
                    schema_enforcement="client_validate",
                    timeout_seconds=45,
                )
            },
        ),
    )
    try:
        result = await gateway.execute(_stage("probe.deepseek"))
    finally:
        await gateway.aclose()
        await llm_gateway.aclose()

    assert result.final_output == ProbePayload(ok=True, label="probe")
    assert result.audit.output_strategy == "json_object"
    assert result.audit.schema_enforcement == "client_validate"
```

Add a second test for the current qwen/default `json_schema` path only if the live provider currently supports it reliably. If not, keep the qwen path covered by unit tests and record that live smoke is DeepSeek-only.

- [ ] **Step 2: Register marker if needed**

If `pyproject.toml` does not declare `live`, add:

```toml
[tool.pytest.ini_options]
markers = [
  "live: opt-in tests that call external provider APIs",
]
```

Preserve existing markers if present.

- [ ] **Step 3: Run skipped test locally**

```bash
uv run pytest tests/live/test_agent_model_capabilities_live.py -q
```

Expected: skipped when `GMGN_LIVE_LLM_SMOKE` is not set.

- [ ] **Step 4: Run live smoke only after config path verification**

```bash
uv run parallax config
GMGN_LIVE_LLM_SMOKE=1 uv run pytest tests/live/test_agent_model_capabilities_live.py -q
```

Expected: pass against the operator-owned config. Do not print API keys or secret env values.

---

## Task 8 - Update Docs And Operator Guidance

**Files:**

- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/CONTRACTS.md`
- Modify: `docs/WORKERS.md`

- [ ] **Step 1: Document execution-plane ownership**

In `docs/ARCHITECTURE.md`, add a short paragraph to the Agent Execution section:

```markdown
Model capability adaptation belongs to the Agent Execution Plane. Domains submit
stage specs with Pydantic output types; they do not branch on provider, model, or
response format. The gateway resolves the lane capability profile and chooses a
structured-output strategy before the provider call.
```

- [ ] **Step 2: Document worker YAML fields**

In `docs/WORKERS.md`, add:

```markdown
agent_runtime.defaults.output_strategy controls the default structured-output
strategy. `json_schema` means provider-enforced schema through the Agents SDK.
`json_object` means provider JSON mode plus application-side Pydantic validation.
Lane overrides may set `provider_family`, `output_strategy`, and
`schema_enforcement` together.
```

Add the DeepSeek example from "Target Config Shape".

- [ ] **Step 3: Document audit semantics**

In `docs/CONTRACTS.md`, add:

```markdown
Agent execution audit includes `provider_family`, `output_strategy`, and
`schema_enforcement`. `schema_enforcement=provider` means the provider enforces
the JSON Schema. `schema_enforcement=client_validate` means the provider is asked
for valid JSON and the application validates the returned object against the
Pydantic schema before domain validation.
```

- [ ] **Step 4: Run docs-adjacent checks**

```bash
uv run pytest tests/architecture/test_agent_execution_plane_contracts.py tests/architecture/test_agent_model_capability_contracts.py -q
```

Expected: pass.

---

## Task 9 - Full Verification

**Files:**

- No new implementation files. This task verifies the branch.

- [ ] **Step 1: Run focused unit and architecture tests**

```bash
uv run pytest \
  tests/unit/test_agent_capabilities.py \
  tests/unit/test_worker_settings.py \
  tests/unit/integrations/openai_agents/test_structured_output_strategy.py \
  tests/unit/integrations/openai_agents/test_agent_execution_gateway.py \
  tests/unit/integrations/openai_agents/test_agent_execution_audit.py \
  tests/unit/test_pulse_decision_agent_client.py \
  tests/architecture/test_agent_execution_plane_contracts.py \
  tests/architecture/test_agent_model_capability_contracts.py \
  -q
```

Expected: pass.

- [ ] **Step 2: Run broad tests that cover provider wiring and workers**

```bash
uv run pytest \
  tests/unit/test_provider_wiring_agent_execution_gateway.py \
  tests/unit/test_providers_wiring.py \
  tests/unit/test_pulse_candidate_worker.py \
  tests/unit/domains/news_intel/test_news_item_brief_worker.py \
  tests/integration/test_api_health.py \
  -q
```

Expected: pass. If integration tests require unavailable services, record the exact unavailable dependency.

- [ ] **Step 3: Run lint**

```bash
uv run ruff check .
```

Expected: pass.

- [ ] **Step 4: Run skipped live smoke**

```bash
uv run pytest tests/live/test_agent_model_capabilities_live.py -q
```

Expected: skipped unless `GMGN_LIVE_LLM_SMOKE=1`.

- [ ] **Step 5: Run live smoke with operator approval/config**

```bash
uv run parallax config
GMGN_LIVE_LLM_SMOKE=1 uv run pytest tests/live/test_agent_model_capabilities_live.py -q
```

Expected: pass for `deepseek-v4-flash` using `json_object/client_validate`. Do not include secret values in logs or reports.

- [ ] **Step 6: Run completion gate if environment supports it**

```bash
make check-all
```

Expected: exit 0. If unavailable, record the failing prerequisite and the focused tests above.

---

## Rollout Plan

- [ ] Ship code with defaults unchanged: existing lanes continue using `qwen3.6` and `json_schema/provider`.
- [ ] Update `~/.parallax/workers.yaml` for one low-risk Pulse lane first:

```yaml
agent_runtime:
  lanes:
    pulse.signal_analyst:
      model: deepseek-v4-flash
      provider_family: deepseek
      output_strategy: json_object
      schema_enforcement: client_validate
```

- [ ] Restart the app container after config edit.
- [ ] Check `/api/status` or ops diagnostics for lane metadata: model, `output_strategy=json_object`, `schema_enforcement=client_validate`.
- [ ] Watch Pulse health for at least one 1h cycle:

```bash
uv run parallax pulse health
```

- [ ] If signal analyst is healthy, move `pulse.bear_case`, then `pulse.risk_portfolio_judge`. Do not switch all lanes at once.
- [ ] Rollback is config-only: set affected lanes back to `qwen3.6` and remove lane capability overrides, then restart. No DB migration rollback should be required.

---

## Acceptance Criteria

- [ ] `deepseek-v4-flash` no longer uses the `json_schema` execution path.
- [ ] `deepseek-v4-flash` live smoke sends `response_format={"type":"json_object"}` and validates the response into the requested Pydantic model.
- [ ] Existing qwen/default lanes still use the current provider-enforced schema path.
- [ ] Pulse domain production files contain no provider/model/response-format logic.
- [ ] LiteLLM is not imported, configured, or added as a dependency.
- [ ] Audit rows and status snapshots distinguish `json_schema/provider` from `json_object/client_validate`.
- [ ] Focused tests, architecture tests, ruff, and opt-in live smoke behavior are recorded in verification.

## Residual Risks

- `json_object` guarantees valid JSON object shape at provider level, not full JSON Schema conformance. The application-side Pydantic validation and retry loop is the enforcement boundary.
- DeepSeek latency and output quality still need production observation; this plan only prevents immediate `response_format` incompatibility and makes failures auditable.
- If future models require forced tools rather than JSON mode, add a new strategy after live probing. Do not overload `json_object` with tool behavior.
