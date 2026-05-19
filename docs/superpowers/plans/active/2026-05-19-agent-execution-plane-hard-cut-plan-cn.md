# Agent Execution Plane Hard Cut Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** Draft
**Date:** 2026-05-19
**Owning spec:** `docs/superpowers/specs/active/2026-05-19-agent-execution-plane-hard-cut-cn.md`
**Worktree:** `.worktrees/agent-execution-plane-hard-cut/`
**Branch:** `codex/agent-execution-plane-hard-cut`

**Goal:** 一次性建立统一 Agent Execution Plane，让 Pulse、Narrative、Social、Watchlist 的 OpenAI Agents SDK 调用共享 lane/bulkhead、timeout、circuit breaker、schema/runner/audit/safety-net 执行层，同时保留各 domain 对 job state、prompt、schema、validator、persistence 的所有权。

**Architecture:** 这是 hard cut，不保留旧 client execution path、旧 `LLMGateway.run_with_limits` 调用路径、双轨开关、legacy fallback、旧 audit 兼容双写。`LLMGateway` 收敛为低层 OpenAI client/trace/export/close primitive；`AgentExecutionGateway` 成为唯一 OpenAI Agents SDK execution path；domain provider adapters 只把 domain stage spec 交给 gateway 执行。

**Tech Stack:** Python 3.13, Pydantic v2, openai-agents, AsyncOpenAI, aiolimiter, psycopg, FastAPI, pytest, ruff, PostgreSQL.

---

## Hard-Cut Rules

- [ ] Do not add `agent_runtime_enabled`, `use_new_gateway`, `legacy_runner`, `fallback_to_old_client`, or any feature flag that allows old execution code to survive.
- [ ] Do not keep `LLMGateway.run_with_limits` for compatibility. After migration, no production code should call it.
- [ ] Do not keep direct `Runner.run`, `Agent(...)`, or `RunConfig(...)` calls inside domain-specific clients. They move into `AgentExecutionGateway`.
- [ ] Do not create a central durable `agent_tasks`, `agent_runs`, or cross-domain execution table.
- [ ] Do not merge domain audit tables. Keep `narrative_model_runs`, `pulse_agent_runs`, `pulse_agent_run_steps`, social `model_runs`, and `watchlist_handle_summary_runs` owned by their domains.
- [ ] Do not let `AgentExecutionGateway` import domain repositories or write domain tables.
- [ ] Do not preserve old Watchlist prompt/schema in `integrations/openai_agents/watchlist_summary_agent_client.py`.
- [ ] Do not dual-write audit metadata only for old readers. If an audit shape changes, update the reader/tests in the same branch.

---

## Pre-flight

- [ ] Read the owning spec fully:
  ```bash
  sed -n '1,560p' docs/superpowers/specs/active/2026-05-19-agent-execution-plane-hard-cut-cn.md
  ```

- [ ] Create isolated worktree:
  ```bash
  git worktree add .worktrees/agent-execution-plane-hard-cut -b codex/agent-execution-plane-hard-cut main
  cd .worktrees/agent-execution-plane-hard-cut
  ```

- [ ] Verify branch and clean status:
  ```bash
  git branch --show-current
  git status --short
  ```
  Expected branch: `codex/agent-execution-plane-hard-cut`; expected status: clean.

- [ ] Confirm runtime config paths before any live-data verification:
  ```bash
  uv run gmgn-twitter-intel config
  ```
  Expected: `config_path` and `workers_config_path` point at `~/.gmgn-twitter-intel/`. Do not print secrets.

- [ ] Capture current direct SDK call sites:
  ```bash
  rg -n "Runner\\.run|Agent\\(|RunConfig\\(" src/gmgn_twitter_intel/integrations/openai_agents
  ```
  Expected before cut: call sites in Pulse, Narrative, Social, Watchlist clients and safety-net. Expected after cut: only gateway and safety-net internals.

- [ ] Run baseline tests:
  ```bash
  uv run ruff check .
  uv run pytest tests/unit/test_llm_gateway.py -q
  uv run pytest tests/unit/integrations/openai_agents -q
  uv run pytest tests/architecture/test_worker_runtime_contracts.py -q
  ```

If integration tests need PostgreSQL and local PostgreSQL is unavailable, record the environment gap and run them before merge in the standard Postgres-backed environment.

---

## Release Shape

Implement as one hard-cut branch. Use small commits for review, but do not deploy a partial state.

Commit groups:

1. Architecture tests that fail on old execution paths.
2. Agent runtime settings and low-level `LLMGateway` cleanup.
3. `AgentExecutionGateway` core types, reservation, circuit breaker, audit, and tests.
4. Provider wiring creates one gateway and closes it.
5. Social client migration.
6. Watchlist prompt/schema relocation and client migration.
7. Narrative client migration.
8. Pulse stage execution migration.
9. Worker reservation/backpressure integration for attempt-on-claim workers.
10. Ops status/metrics/docs/verification.

No group may introduce a compatibility path. If a migrated client needs a fallback for tests, use a fake `AgentExecutor` injected into `AgentExecutionGateway`, not the old client code.

---

## File Structure

### Create

- `src/gmgn_twitter_intel/integrations/openai_agents/agent_execution_types.py`
  - Owns `AgentLaneKey`, `AgentCircuitBreakerPolicy`, `AgentLanePolicy`, `AgentRuntimePolicy`, `AgentStageSpec`, `AgentExecutionRequestAudit`, `AgentExecutionResultAudit`, `AgentExecutionResult`, `AgentExecutionError`, `AgentExecutionErrorClass`, and `AgentCapacityReservation`.

- `src/gmgn_twitter_intel/integrations/openai_agents/agent_execution_gateway.py`
  - Owns lane reservation, global/per-lane semaphores, circuit state, `Agent`/`RunConfig` construction, `Runner.run`, safety-net execution, usage extraction, audit envelope, and status snapshot.

- `src/gmgn_twitter_intel/integrations/openai_agents/agent_hashing.py`
  - Owns `json_sha256`, `text_sha256`, `trace_id_for`, and `artifact_hash_for`.

- `src/gmgn_twitter_intel/domains/watchlist_intel/types/handle_summary_agent.py`
  - Owns Watchlist summary Pydantic payloads and constants currently embedded in the OpenAI client.

- `src/gmgn_twitter_intel/domains/watchlist_intel/prompts/handle_summary.md`
  - Owns Watchlist summary prompt text.

- `src/gmgn_twitter_intel/domains/watchlist_intel/services/handle_summary_runtime.py`
  - Owns Watchlist `AgentStageSpec` construction and input payload.

- `tests/unit/integrations/openai_agents/test_agent_execution_gateway.py`
- `tests/unit/integrations/openai_agents/test_agent_execution_audit.py`
- `tests/unit/integrations/openai_agents/test_agent_runtime_policy.py`
- `tests/unit/test_provider_wiring_agent_execution_gateway.py`
- `tests/unit/domains/watchlist_intel/test_handle_summary_runtime.py`
- `tests/architecture/test_agent_execution_plane_contracts.py`

### Modify

- `src/gmgn_twitter_intel/app/runtime/llm_gateway.py`
- `src/gmgn_twitter_intel/app/runtime/bootstrap.py`
- `src/gmgn_twitter_intel/app/runtime/provider_wiring/openai.py`
- `src/gmgn_twitter_intel/app/runtime/provider_wiring/types.py`
- `src/gmgn_twitter_intel/platform/config/settings.py`
- `src/gmgn_twitter_intel/integrations/openai_agents/__init__.py`
- `src/gmgn_twitter_intel/integrations/openai_agents/instructor_safety_net.py`
- `src/gmgn_twitter_intel/integrations/openai_agents/social_event_agent_client.py`
- `src/gmgn_twitter_intel/integrations/openai_agents/watchlist_summary_agent_client.py`
- `src/gmgn_twitter_intel/integrations/openai_agents/narrative_intel_agent_client.py`
- `src/gmgn_twitter_intel/integrations/openai_agents/pulse_decision_agent_client.py`
- `src/gmgn_twitter_intel/domains/social_enrichment/types/social_event_extraction.py`
- `src/gmgn_twitter_intel/domains/watchlist_intel/interfaces.py`
- `src/gmgn_twitter_intel/domains/watchlist_intel/runtime/handle_summary_worker.py`
- `src/gmgn_twitter_intel/domains/watchlist_intel/services/handle_summary_service.py`
- `src/gmgn_twitter_intel/domains/narrative_intel/providers.py`
- `src/gmgn_twitter_intel/domains/pulse_lab/types/agent_decision.py`
- `src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_decision_runtime.py`
- `src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_candidate_job_service.py`
- `src/gmgn_twitter_intel/domains/pulse_lab/runtime/pulse_candidate_worker.py`
- `src/gmgn_twitter_intel/domains/social_enrichment/runtime/enrichment_worker.py`
- `tests/unit/test_llm_gateway.py`
- `tests/unit/test_worker_settings.py`
- `tests/unit/test_bootstrap_worker_runtime_wiring.py`
- `tests/architecture/test_worker_runtime_contracts.py`
- `docs/ARCHITECTURE.md`
- `docs/WORKERS.md`
- `docs/CONTRACTS.md`
- `docs/RELIABILITY.md`
- `docs/superpowers/specs/active/2026-05-15-worker-runtime-platform-cn.md`

### Delete Or Fold Away

- Delete duplicated `_api_base`, `_trace_id`, `_sha256`, and usage extraction helpers from domain-specific OpenAI clients after `agent_hashing.py` and gateway utilities exist.
- Delete direct client-owned `_build_model()` methods after model creation moves to `AgentExecutionGateway`.
- Delete Watchlist payload classes and `_instructions()` from `watchlist_summary_agent_client.py`.
- Delete old `LLMGateway.run_with_limits`, `last_worker_name`, and `last_stage`.

---

## Task 1 - Architecture Guardrails First

**Files:**

- Create: `tests/architecture/test_agent_execution_plane_contracts.py`
- Modify: `tests/architecture/test_worker_runtime_contracts.py`

- [ ] **Step 1: Add failing architecture tests for SDK execution boundary**

Create `tests/architecture/test_agent_execution_plane_contracts.py`:

```python
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "gmgn_twitter_intel"
OPENAI_AGENTS = SRC / "integrations" / "openai_agents"
GATEWAY_FILES = {
    OPENAI_AGENTS / "agent_execution_gateway.py",
    OPENAI_AGENTS / "instructor_safety_net.py",
}


def _py_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.py") if "__pycache__" not in path.parts)


def _parse(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _imported_modules(tree: ast.AST) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_call_name(node.value)}.{node.attr}"
    return ""


def test_openai_agents_sdk_execution_only_in_gateway() -> None:
    violations: list[str] = []
    for path in _py_files(OPENAI_AGENTS):
        if path in GATEWAY_FILES:
            continue
        tree = _parse(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = _call_name(node.func)
                if name in {"Agent", "RunConfig"} or name.endswith(".run") or name == "Runner.run":
                    violations.append(f"{path.relative_to(ROOT)}:{node.lineno} calls {name}")

    assert violations == []


def test_async_openai_constructed_only_by_llm_gateway_or_safety_net() -> None:
    allowlist = {
        SRC / "app" / "runtime" / "llm_gateway.py",
        OPENAI_AGENTS / "instructor_safety_net.py",
    }
    violations: list[str] = []
    for path in _py_files(SRC):
        if path in allowlist:
            continue
        for node in ast.walk(_parse(path)):
            if isinstance(node, ast.Call) and _call_name(node.func) == "AsyncOpenAI":
                violations.append(f"{path.relative_to(ROOT)}:{node.lineno} constructs AsyncOpenAI")

    assert violations == []


def test_agent_execution_gateway_does_not_import_domain_repositories() -> None:
    gateway = OPENAI_AGENTS / "agent_execution_gateway.py"
    if not gateway.exists():
        raise AssertionError("agent_execution_gateway.py must exist")
    imports = _imported_modules(_parse(gateway))
    violations = sorted(module for module in imports if ".repositories" in module or module.endswith(".repositories"))
    assert violations == []


def test_domain_packages_do_not_import_openai_agents_sdk() -> None:
    domain_root = SRC / "domains"
    forbidden_prefixes = ("agents", "agents.", "openai")
    violations: list[str] = []
    for path in _py_files(domain_root):
        imports = _imported_modules(_parse(path))
        for module in sorted(imports):
            if module.startswith(forbidden_prefixes):
                violations.append(f"{path.relative_to(ROOT)} imports {module}")

    assert violations == []


def test_watchlist_prompt_not_owned_by_openai_integration() -> None:
    path = OPENAI_AGENTS / "watchlist_summary_agent_client.py"
    if not path.exists():
        raise AssertionError("watchlist_summary_agent_client.py must exist")
    text = path.read_text(encoding="utf-8")
    assert "You summarize a watched crypto Twitter account" not in text
    assert "WatchlistHandleSummaryPayload" not in text
```

- [ ] **Step 2: Add WorkerBase run override guard**

In `tests/architecture/test_worker_runtime_contracts.py`, add:

```python
@pytest.mark.architecture
def test_long_running_workers_do_not_override_worker_base_run_without_allowlist() -> None:
    allowlist = {
        "live_price_gateway",
    }
    violations: list[str] = []
    for worker_key, qualified_name in EXPECTED_WORKERS.items():
        worker_class = _import_qualified_name(qualified_name)
        if worker_key in allowlist:
            continue
        if "run" in worker_class.__dict__:
            violations.append(f"{worker_key} overrides run()")

    assert violations == []
```

- [ ] **Step 3: Run tests and confirm they fail on current code**

```bash
uv run pytest tests/architecture/test_agent_execution_plane_contracts.py -q
uv run pytest tests/architecture/test_worker_runtime_contracts.py::test_long_running_workers_do_not_override_worker_base_run_without_allowlist -q
```

Expected: first command fails because `agent_execution_gateway.py` does not exist and current clients call `Agent`, `RunConfig`, and `Runner.run`; second command passes or only flags intentional allowlist.

- [ ] **Step 4: Commit**

```bash
git add tests/architecture/test_agent_execution_plane_contracts.py tests/architecture/test_worker_runtime_contracts.py
git commit -m "test: guard agent execution plane boundaries"
```

---

## Task 2 - Agent Runtime Settings

**Files:**

- Modify: `src/gmgn_twitter_intel/platform/config/settings.py`
- Modify: `tests/unit/test_worker_settings.py`
- Modify: `tests/architecture/test_worker_runtime_contracts.py`

- [ ] **Step 1: Add failing settings tests**

In `tests/unit/test_worker_settings.py`, add:

```python
def test_agent_runtime_settings_default_lanes() -> None:
    from gmgn_twitter_intel.platform.config.settings import WorkersSettings

    settings = WorkersSettings()

    assert settings.agent_runtime.global_max_concurrency == 4
    assert settings.agent_runtime.global_rpm_limit == 60
    assert settings.agent_runtime.lanes["pulse.decision_maker"].priority == "high"
    assert settings.agent_runtime.lanes["narrative.mention_semantics"].priority == "bulk"
    assert settings.agent_runtime.lanes["watchlist.handle_summary"].priority == "low"


def test_agent_runtime_settings_parse_workers_yaml_shape() -> None:
    from gmgn_twitter_intel.platform.config.settings import WorkersSettings

    settings = WorkersSettings(
        agent_runtime={
            "global_max_concurrency": 2,
            "global_rpm_limit": 30,
            "lanes": {
                "pulse.decision_maker": {
                    "priority": "high",
                    "max_concurrency": 1,
                    "timeout_seconds": 90,
                    "circuit_breaker": {
                        "failure_threshold": 3,
                        "window_seconds": 120,
                        "open_seconds": 60,
                    },
                }
            },
        }
    )

    lane = settings.agent_runtime.lanes["pulse.decision_maker"]
    assert settings.agent_runtime.global_max_concurrency == 2
    assert settings.agent_runtime.global_rpm_limit == 30
    assert lane.timeout_seconds == 90
    assert lane.circuit_breaker.failure_threshold == 3
```

- [ ] **Step 2: Implement settings models**

Add these classes near `BackoffPolicy` in `settings.py`:

```python
class AgentCircuitBreakerSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    failure_threshold: int = Field(default=5, ge=1)
    window_seconds: int = Field(default=300, ge=1)
    open_seconds: int = Field(default=120, ge=1)


class AgentLaneSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    priority: Literal["high", "normal", "bulk", "low"] = "normal"
    max_concurrency: int = Field(default=1, ge=1)
    timeout_seconds: float = Field(default=120.0, ge=1)
    rpm_limit: int | None = Field(default=None, ge=1)
    circuit_breaker: AgentCircuitBreakerSettings = Field(default_factory=AgentCircuitBreakerSettings)


def _default_agent_lanes() -> dict[str, AgentLaneSettings]:
    return {
        "pulse.pipeline": AgentLaneSettings(priority="high", max_concurrency=1, timeout_seconds=240.0),
        "pulse.evidence_debate": AgentLaneSettings(priority="high", max_concurrency=1, timeout_seconds=120.0),
        "pulse.decision_maker": AgentLaneSettings(priority="high", max_concurrency=1, timeout_seconds=120.0),
        "narrative.mention_semantics": AgentLaneSettings(priority="bulk", max_concurrency=1, timeout_seconds=120.0),
        "narrative.discussion_digest": AgentLaneSettings(priority="normal", max_concurrency=1, timeout_seconds=120.0),
        "social.event_enrichment": AgentLaneSettings(priority="normal", max_concurrency=2, timeout_seconds=120.0),
        "watchlist.handle_summary": AgentLaneSettings(priority="low", max_concurrency=1, timeout_seconds=120.0),
        "news.fact_candidate": AgentLaneSettings(priority="low", max_concurrency=1, timeout_seconds=120.0),
    }


class AgentRuntimeSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    global_max_concurrency: int = Field(default=4, ge=1)
    global_rpm_limit: int = Field(default=60, ge=1)
    lanes: dict[str, AgentLaneSettings] = Field(default_factory=_default_agent_lanes)
```

Add to `WorkersSettings`:

```python
agent_runtime: AgentRuntimeSettings = Field(default_factory=AgentRuntimeSettings)
```

- [ ] **Step 3: Update worker inventory architecture test**

In `test_worker_registry_matches_workers_yaml_schema`, change settings key calculation to:

```python
settings_keys = set(WorkersSettings.model_fields) - {"defaults", "agent_runtime"}
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/unit/test_worker_settings.py -q
uv run pytest tests/architecture/test_worker_runtime_contracts.py::test_worker_registry_matches_workers_yaml_schema -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add src/gmgn_twitter_intel/platform/config/settings.py tests/unit/test_worker_settings.py tests/architecture/test_worker_runtime_contracts.py
git commit -m "feat: add agent runtime lane settings"
```

---

## Task 3 - Make `LLMGateway` Transport-Only

**Files:**

- Modify: `src/gmgn_twitter_intel/app/runtime/llm_gateway.py`
- Modify: `tests/unit/test_llm_gateway.py`

- [ ] **Step 1: Rewrite tests away from `run_with_limits`**

Delete tests:

- `test_run_with_limits_serializes_global_concurrency`
- `test_run_with_limits_applies_timeout`

Add:

```python
def test_llm_gateway_no_longer_exposes_execution_limit_api() -> None:
    gateway = LLMGateway(api_key="sk-test", trace_enabled=False)

    assert not hasattr(gateway, "run_with_limits")
    assert not hasattr(gateway, "last_worker_name")
    assert not hasattr(gateway, "last_stage")
```

Keep trace export and `openai_client` tests.

- [ ] **Step 2: Remove old execution methods**

In `llm_gateway.py`:

- remove `asyncio`, `Awaitable`, `Callable`, `TypeVar`, `AsyncLimiter`;
- remove `DEFAULT_MAX_CONCURRENCY`, `DEFAULT_RPM_LIMIT`;
- remove `self._semaphore`, `self._limiter`, `last_worker_name`, `last_stage`;
- remove `run_with_limits`.

Constructor should become:

```python
class LLMGateway:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        trace_enabled: bool = True,
        trace_api_key: str | None = None,
    ) -> None:
        self.api_key = str(api_key or "")
        self.base_url = _api_base(base_url)
        self._clients: list[Any] = []
        tracing_export_key = str(trace_api_key or "").strip()
        if not tracing_export_key and _is_openai_base_url(self.base_url):
            tracing_export_key = self.api_key
        self.trace_export_enabled = bool(trace_enabled and tracing_export_key)
        if self.trace_export_enabled:
            set_tracing_export_api_key(tracing_export_key)
```

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/unit/test_llm_gateway.py -q
```

Expected: pass.

- [ ] **Step 4: Commit**

```bash
git add src/gmgn_twitter_intel/app/runtime/llm_gateway.py tests/unit/test_llm_gateway.py
git commit -m "refactor: make llm gateway transport only"
```

---

## Task 4 - Agent Execution Types And Hashing

**Files:**

- Create: `src/gmgn_twitter_intel/integrations/openai_agents/agent_hashing.py`
- Create: `src/gmgn_twitter_intel/integrations/openai_agents/agent_execution_types.py`
- Create: `tests/unit/integrations/openai_agents/test_agent_execution_audit.py`

- [ ] **Step 1: Add tests for stable hashes and audit models**

Create `tests/unit/integrations/openai_agents/test_agent_execution_audit.py`:

```python
from __future__ import annotations

from gmgn_twitter_intel.integrations.openai_agents.agent_execution_types import (
    AgentExecutionErrorClass,
    AgentExecutionRequestAudit,
    AgentLanePolicy,
    AgentRuntimePolicy,
    AgentStageSpec,
)
from gmgn_twitter_intel.integrations.openai_agents.agent_hashing import artifact_hash_for, json_sha256, trace_id_for


def test_hash_helpers_are_stable() -> None:
    assert json_sha256({"b": 2, "a": 1}) == json_sha256({"a": 1, "b": 2})
    assert trace_id_for("run-1").startswith("trace_")
    assert artifact_hash_for(
        model="qwen3.6",
        prompt_version="p1",
        schema_version="s1",
        runtime_version="r1",
        output_schema_hash="schema-hash",
    ).startswith("sha256:")


def test_agent_stage_spec_request_audit_shape() -> None:
    spec = AgentStageSpec(
        lane="social.event_enrichment",
        stage="social_event",
        model="qwen3.6",
        instructions="Return JSON.",
        input_payload="{\"event_id\":\"e1\"}",
        output_type=dict,
        prompt_version="p1",
        schema_version="s1",
        workflow_name="workflow",
        agent_name="agent",
        group_id="e1",
        trace_metadata={"event_id": "e1"},
    )
    audit = AgentExecutionRequestAudit.from_stage(spec, trace_id="trace_abc", artifact_version_hash="sha256:abc")

    assert audit.provider == "openai"
    assert audit.backend == "openai_agents_sdk"
    assert audit.lane == "social.event_enrichment"
    assert audit.stage == "social_event"
    assert audit.execution_started is False
    assert audit.usage == {}
    assert audit.trace_metadata["event_id"] == "e1"


def test_runtime_policy_uses_default_lane_when_missing() -> None:
    policy = AgentRuntimePolicy(
        global_max_concurrency=2,
        global_rpm_limit=30,
        lanes={"known": AgentLanePolicy(priority="high", max_concurrency=1, timeout_seconds=15)},
    )

    known = policy.lane_for("known")
    missing = policy.lane_for("missing")

    assert known.timeout_seconds == 15
    assert missing.timeout_seconds == 120
    assert AgentExecutionErrorClass.TIMEOUT.value == "timeout"
```

- [ ] **Step 2: Add hashing helpers**

Create `agent_hashing.py`:

```python
from __future__ import annotations

import hashlib
import json
from typing import Any


def json_sha256(value: Any) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return "sha256:" + hashlib.sha256(data).hexdigest()


def text_sha256(value: str) -> str:
    return "sha256:" + hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def trace_id_for(value: str, *, length: int = 32) -> str:
    digest = hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()
    return "trace_" + digest[: max(8, int(length))]


def artifact_hash_for(
    *,
    model: str,
    prompt_version: str,
    schema_version: str,
    runtime_version: str,
    output_schema_hash: str,
) -> str:
    return json_sha256(
        {
            "model": model,
            "prompt_version": prompt_version,
            "schema_version": schema_version,
            "runtime_version": runtime_version,
            "output_schema_hash": output_schema_hash,
        }
    )


__all__ = ["artifact_hash_for", "json_sha256", "text_sha256", "trace_id_for"]
```

- [ ] **Step 3: Add execution types**

Create `agent_execution_types.py` with Pydantic models and dataclasses:

```python
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from gmgn_twitter_intel.integrations.openai_agents.agent_hashing import json_sha256


RUNTIME_VERSION = "agent-execution-plane-v1"


class AgentExecutionErrorClass(str, Enum):
    CAPACITY_DENIED = "capacity_denied"
    CIRCUIT_OPEN = "circuit_open"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    TRANSPORT_ERROR = "transport_error"
    PROVIDER_ERROR = "provider_error"
    SCHEMA_INVALID = "schema_invalid"
    DOMAIN_VALIDATION_FAILED = "domain_validation_failed"
    DETERMINISTIC_NO_INPUT = "deterministic_no_input"


class AgentCircuitBreakerPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    failure_threshold: int = Field(default=5, ge=1)
    window_seconds: int = Field(default=300, ge=1)
    open_seconds: int = Field(default=120, ge=1)


class AgentLanePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    priority: str = "normal"
    max_concurrency: int = Field(default=1, ge=1)
    timeout_seconds: float = Field(default=120.0, ge=1)
    rpm_limit: int | None = Field(default=None, ge=1)
    circuit_breaker: AgentCircuitBreakerPolicy = Field(default_factory=AgentCircuitBreakerPolicy)


class AgentRuntimePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    global_max_concurrency: int = Field(default=4, ge=1)
    global_rpm_limit: int = Field(default=60, ge=1)
    lanes: dict[str, AgentLanePolicy] = Field(default_factory=dict)

    def lane_for(self, lane: str) -> AgentLanePolicy:
        return self.lanes.get(str(lane), AgentLanePolicy())


class AgentStageSpec(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    lane: str
    stage: str
    model: str
    instructions: str
    input_payload: Any
    output_type: Any
    prompt_version: str
    schema_version: str
    workflow_name: str
    agent_name: str
    group_id: str = ""
    trace_metadata: dict[str, Any] = Field(default_factory=dict)
    max_turns: int = Field(default=1, ge=1)
    tools: list[Any] = Field(default_factory=list)

    @property
    def input_hash(self) -> str:
        return json_sha256(self.input_payload)


class AgentExecutionRequestAudit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = "openai"
    backend: str = "openai_agents_sdk"
    model: str
    lane: str
    stage: str
    workflow_name: str
    agent_name: str
    sdk_trace_id: str
    group_id: str
    prompt_version: str
    schema_version: str
    runtime_version: str = RUNTIME_VERSION
    artifact_version_hash: str
    input_hash: str
    output_hash: str | None = None
    latency_ms: float | None = None
    usage: dict[str, Any] = Field(default_factory=dict)
    parse_mode: str | None = None
    safety_net: dict[str, Any] = Field(default_factory=dict)
    trace_metadata: dict[str, Any] = Field(default_factory=dict)
    execution_started: bool = False
    status: str = "planned"
    error_class: str | None = None
    error_message: str | None = None

    @classmethod
    def from_stage(
        cls,
        stage: AgentStageSpec,
        *,
        trace_id: str,
        artifact_version_hash: str,
    ) -> AgentExecutionRequestAudit:
        trace_metadata = {
            **stage.trace_metadata,
            "backend": "openai_agents_sdk",
            "model": stage.model,
            "lane": stage.lane,
            "stage": stage.stage,
            "prompt_version": stage.prompt_version,
            "schema_version": stage.schema_version,
            "runtime_version": RUNTIME_VERSION,
            "artifact_version_hash": artifact_version_hash,
            "input_hash": stage.input_hash,
        }
        return cls(
            model=stage.model,
            lane=stage.lane,
            stage=stage.stage,
            workflow_name=stage.workflow_name,
            agent_name=stage.agent_name,
            sdk_trace_id=trace_id,
            group_id=stage.group_id,
            prompt_version=stage.prompt_version,
            schema_version=stage.schema_version,
            artifact_version_hash=artifact_version_hash,
            input_hash=stage.input_hash,
            trace_metadata=trace_metadata,
        )


class AgentExecutionResultAudit(AgentExecutionRequestAudit):
    status: str


class AgentExecutionResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    final_output: Any
    audit: AgentExecutionResultAudit
    raw_result: Any | None = None


class AgentExecutionError(Exception):
    def __init__(
        self,
        error_class: AgentExecutionErrorClass,
        message: str,
        *,
        audit: AgentExecutionRequestAudit | AgentExecutionResultAudit | None = None,
        execution_started: bool = False,
    ) -> None:
        super().__init__(message)
        self.error_class = error_class
        self.audit = audit
        self.execution_started = bool(execution_started)


@dataclass(slots=True)
class AgentCapacityReservation:
    lane: str
    acquired: bool
    reason: AgentExecutionErrorClass | None = None
    _release: Any | None = None

    async def release(self) -> None:
        if self._release is not None:
            self._release()
            self._release = None


__all__ = [
    "AgentCapacityReservation",
    "AgentCircuitBreakerPolicy",
    "AgentExecutionError",
    "AgentExecutionErrorClass",
    "AgentExecutionRequestAudit",
    "AgentExecutionResult",
    "AgentExecutionResultAudit",
    "AgentLanePolicy",
    "AgentRuntimePolicy",
    "AgentStageSpec",
    "RUNTIME_VERSION",
]
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/unit/integrations/openai_agents/test_agent_execution_audit.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add src/gmgn_twitter_intel/integrations/openai_agents/agent_hashing.py src/gmgn_twitter_intel/integrations/openai_agents/agent_execution_types.py tests/unit/integrations/openai_agents/test_agent_execution_audit.py
git commit -m "feat: add agent execution types"
```

---

## Task 5 - AgentExecutionGateway Core

**Files:**

- Create: `src/gmgn_twitter_intel/integrations/openai_agents/agent_execution_gateway.py`
- Modify: `src/gmgn_twitter_intel/integrations/openai_agents/instructor_safety_net.py`
- Create: `tests/unit/integrations/openai_agents/test_agent_execution_gateway.py`
- Create: `tests/unit/integrations/openai_agents/test_agent_runtime_policy.py`

- [ ] **Step 1: Add gateway tests**

Create `tests/unit/integrations/openai_agents/test_agent_execution_gateway.py` with fake runner/safety net:

```python
from __future__ import annotations

import asyncio

import pytest
from pydantic import BaseModel

from gmgn_twitter_intel.integrations.openai_agents.agent_execution_gateway import AgentExecutionGateway
from gmgn_twitter_intel.integrations.openai_agents.agent_execution_types import (
    AgentExecutionError,
    AgentExecutionErrorClass,
    AgentLanePolicy,
    AgentRuntimePolicy,
    AgentStageSpec,
)


class Payload(BaseModel):
    value: str


class FakeResult:
    def __init__(self, final_output):
        self.final_output = final_output
        self.usage = {"input_tokens": 3, "output_tokens": 4}


class FakeRunner:
    def __init__(self) -> None:
        self.calls = 0

    async def run(self, agent, input_payload, *, max_turns, run_config):
        self.calls += 1
        return FakeResult(Payload(value="ok"))


class FakeLLMGateway:
    trace_export_enabled = False

    def openai_client(self, *, model: str, base_url: str, timeout_s: float):
        return object()


def _spec(lane: str = "test.lane") -> AgentStageSpec:
    return AgentStageSpec(
        lane=lane,
        stage="stage",
        model="qwen3.6",
        instructions="Return JSON.",
        input_payload={"x": 1},
        output_type=Payload,
        prompt_version="p1",
        schema_version="s1",
        workflow_name="workflow",
        agent_name="agent",
        group_id="g1",
    )


def test_execute_returns_normalized_audit() -> None:
    async def scenario() -> None:
        runner = FakeRunner()
        gateway = AgentExecutionGateway(
            llm_gateway=FakeLLMGateway(),
            base_url="https://example.com/v1",
            trace_enabled=False,
            trace_include_sensitive_data=False,
            policy=AgentRuntimePolicy(
                global_max_concurrency=1,
                global_rpm_limit=1000,
                lanes={"test.lane": AgentLanePolicy(max_concurrency=1, timeout_seconds=10)},
            ),
            runner=runner,
        )

        result = await gateway.execute(_spec())

        assert isinstance(result.final_output, Payload)
        assert result.audit.status == "done"
        assert result.audit.execution_started is True
        assert result.audit.usage == {"input_tokens": 3, "output_tokens": 4}
        assert result.audit.parse_mode == "strict"
        assert result.audit.output_hash is not None
        assert runner.calls == 1

    asyncio.run(scenario())


def test_try_reserve_denies_when_lane_full() -> None:
    async def scenario() -> None:
        gateway = AgentExecutionGateway(
            llm_gateway=FakeLLMGateway(),
            base_url="https://example.com/v1",
            trace_enabled=False,
            trace_include_sensitive_data=False,
            policy=AgentRuntimePolicy(
                global_max_concurrency=1,
                global_rpm_limit=1000,
                lanes={"test.lane": AgentLanePolicy(max_concurrency=1, timeout_seconds=10)},
            ),
            runner=FakeRunner(),
        )

        first = gateway.try_reserve("test.lane")
        second = gateway.try_reserve("test.lane")

        assert first.acquired is True
        assert second.acquired is False
        assert second.reason == AgentExecutionErrorClass.CAPACITY_DENIED

        await first.release()
        third = gateway.try_reserve("test.lane")
        assert third.acquired is True
        await third.release()

    asyncio.run(scenario())


def test_circuit_open_fails_fast_without_runner_call() -> None:
    async def scenario() -> None:
        runner = FakeRunner()
        gateway = AgentExecutionGateway(
            llm_gateway=FakeLLMGateway(),
            base_url="https://example.com/v1",
            trace_enabled=False,
            trace_include_sensitive_data=False,
            policy=AgentRuntimePolicy(
                global_max_concurrency=1,
                global_rpm_limit=1000,
                lanes={
                    "test.lane": AgentLanePolicy(
                        max_concurrency=1,
                        timeout_seconds=10,
                        circuit_breaker={"failure_threshold": 1, "window_seconds": 60, "open_seconds": 60},
                    )
                },
            ),
            runner=runner,
        )
        gateway.record_lane_failure("test.lane")

        with pytest.raises(AgentExecutionError) as err:
            await gateway.execute(_spec())

        assert err.value.error_class == AgentExecutionErrorClass.CIRCUIT_OPEN
        assert err.value.execution_started is False
        assert runner.calls == 0

    asyncio.run(scenario())
```

- [ ] **Step 2: Implement `AgentExecutionGateway`**

Create `agent_execution_gateway.py`. Keep the first version compact; no durable tables and no domain imports.

Required public methods:

```python
class AgentExecutionGateway:
    def __init__(
        self,
        *,
        llm_gateway: Any,
        base_url: str,
        trace_enabled: bool,
        trace_include_sensitive_data: bool,
        policy: AgentRuntimePolicy,
        runner: Any | None = None,
        safety_net: InstructorSafetyNet | None = None,
    ) -> None: ...

    def request_audit(self, stage: AgentStageSpec) -> AgentExecutionRequestAudit: ...

    def try_reserve(self, lane: str) -> AgentCapacityReservation: ...

    async def execute(self, stage: AgentStageSpec) -> AgentExecutionResult: ...

    def record_lane_failure(self, lane: str) -> None: ...

    def status_snapshot(self) -> dict[str, Any]: ...

    async def aclose(self) -> None: ...
```

Implementation rules:

- Use `asyncio.BoundedSemaphore` for global and per-lane slots.
- `try_reserve` must not await. It should inspect semaphore state and acquire immediately only when both global and lane slots are available.
- `execute` may acquire slots internally if caller did not reserve; callers that burn attempts before claim will use `try_reserve` explicitly.
- Apply `asyncio.wait_for` with lane timeout.
- Use `AsyncLimiter(policy.global_rpm_limit, 60)`.
- Build `Agent` with `StrictJsonOutputSchema(stage.output_type)`.
- Build `RunConfig` with `stage.workflow_name`, generated trace id, `stage.group_id`, trace flags, and request audit metadata.
- Use `InstructorSafetyNet.run_with_safety_net(..., return_result=True)` when safety net is configured.
- Extract usage into top-level audit.
- Classify `TimeoutError` as `timeout`, schema/model behavior errors as `schema_invalid`, other provider exceptions as `provider_error`.
- Record circuit failures for timeout, rate-limited, transport, provider, and schema errors.

- [ ] **Step 3: Move shared usage extraction into gateway-accessible function**

In `instructor_safety_net.py`, export the existing usage helper without changing safety-net semantics:

```python
__all__ = ["InstructorSafetyNet", "SafetyNetExhausted", "_extract_sdk_usage"]
```

Gateway may import `_extract_sdk_usage` for now. If the leading underscore feels too sharp during implementation, rename it to `extract_sdk_usage` in this same task and update imports/tests in one commit.

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/unit/integrations/openai_agents/test_agent_execution_gateway.py tests/unit/integrations/openai_agents/test_agent_execution_audit.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add src/gmgn_twitter_intel/integrations/openai_agents/agent_execution_gateway.py src/gmgn_twitter_intel/integrations/openai_agents/instructor_safety_net.py tests/unit/integrations/openai_agents/test_agent_execution_gateway.py
git commit -m "feat: add agent execution gateway"
```

---

## Task 6 - Provider Wiring Creates One Gateway

**Files:**

- Modify: `src/gmgn_twitter_intel/app/runtime/bootstrap.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/provider_wiring/openai.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/provider_wiring/types.py`
- Create: `tests/unit/test_provider_wiring_agent_execution_gateway.py`

- [ ] **Step 1: Add provider wiring test**

Create `tests/unit/test_provider_wiring_agent_execution_gateway.py`:

```python
from __future__ import annotations

from gmgn_twitter_intel.app.runtime.provider_wiring.openai import build_agent_execution_gateway
from gmgn_twitter_intel.platform.config.settings import Settings


class FakeLLMGateway:
    trace_export_enabled = False


def test_build_agent_execution_gateway_uses_workers_agent_runtime_settings() -> None:
    settings = Settings(
        llm={"api_key": "sk-test", "model": "qwen3.6", "base_url": "https://example.com/v1"},
        workers={
            "agent_runtime": {
                "global_max_concurrency": 2,
                "global_rpm_limit": 30,
                "lanes": {
                    "pulse.decision_maker": {
                        "priority": "high",
                        "max_concurrency": 1,
                        "timeout_seconds": 90,
                    }
                },
            }
        },
    )

    gateway = build_agent_execution_gateway(settings, llm_gateway=FakeLLMGateway())

    snapshot = gateway.status_snapshot()
    assert snapshot["global_max_concurrency"] == 2
    assert snapshot["lanes"]["pulse.decision_maker"]["timeout_seconds"] == 90
```

- [ ] **Step 2: Add `build_agent_execution_gateway`**

In `provider_wiring/openai.py`, add:

```python
def build_agent_execution_gateway(settings: Settings, *, llm_gateway: object | None) -> AgentExecutionGateway:
    gateway = _require_llm_gateway(llm_gateway)
    policy = AgentRuntimePolicy.model_validate(settings.workers.agent_runtime.model_dump(mode="json"))
    safety_net = _build_safety_net(settings, model=settings.llm_model or "")
    return AgentExecutionGateway(
        llm_gateway=gateway,
        base_url=settings.llm_base_url,
        trace_enabled=settings.llm_trace_enabled,
        trace_include_sensitive_data=settings.llm_trace_include_sensitive_data,
        policy=policy,
        safety_net=safety_net,
    )
```

Do not keep separate safety-net instances per client. The gateway owns safety-net lifecycle.

- [ ] **Step 3: Change provider factory signatures**

Factories should accept `agent_gateway`, not `safety_net` and not direct runner execution primitives:

```python
def openai_social_event_provider(settings: Settings, *, agent_gateway: AgentExecutionGateway) -> OpenAIAgentsSocialEventClient: ...
def openai_pulse_decision_provider(settings: Settings, *, agent_gateway: AgentExecutionGateway, db_pool: Any | None) -> OpenAIPulseDecisionProvider: ...
def openai_narrative_intel_provider(settings: Settings, *, agent_gateway: AgentExecutionGateway) -> OpenAINarrativeIntelProvider: ...
def openai_watchlist_summary_provider(settings: Settings, *, agent_gateway: AgentExecutionGateway) -> OpenAIAgentsWatchlistSummaryClient: ...
```

No factory should instantiate `InstructorSafetyNet` except `build_agent_execution_gateway`.

- [ ] **Step 4: Update bootstrap**

In `bootstrap.py`, runtime construction should create:

```python
llm_gateway = LLMGateway.create(settings) if any_llm_configured else None
agent_execution_gateway = (
    build_agent_execution_gateway(settings, llm_gateway=llm_gateway)
    if llm_gateway is not None
    else None
)
```

Runtime close path must close `agent_execution_gateway` before or alongside `llm_gateway`.

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/unit/test_provider_wiring_agent_execution_gateway.py tests/unit/test_bootstrap_worker_runtime_wiring.py -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add src/gmgn_twitter_intel/app/runtime/bootstrap.py src/gmgn_twitter_intel/app/runtime/provider_wiring/openai.py src/gmgn_twitter_intel/app/runtime/provider_wiring/types.py tests/unit/test_provider_wiring_agent_execution_gateway.py
git commit -m "feat: wire shared agent execution gateway"
```

---

## Task 7 - Migrate Social Event Client

**Files:**

- Modify: `src/gmgn_twitter_intel/integrations/openai_agents/social_event_agent_client.py`
- Modify: `src/gmgn_twitter_intel/domains/social_enrichment/types/social_event_extraction.py`
- Modify: `src/gmgn_twitter_intel/domains/social_enrichment/runtime/enrichment_worker.py`
- Add/modify: `tests/unit/integrations/openai_agents/test_social_event_agent_client.py`

- [ ] **Step 1: Add client test**

Create or update `tests/unit/integrations/openai_agents/test_social_event_agent_client.py`:

```python
from __future__ import annotations

from gmgn_twitter_intel.integrations.openai_agents.social_event_agent_client import OpenAIAgentsSocialEventClient


class FakeGateway:
    def __init__(self) -> None:
        self.stage = None

    def request_audit(self, stage):
        self.stage = stage
        return {"lane": stage.lane, "stage": stage.stage, "usage": {}, "execution_started": False}

    async def execute(self, stage):
        self.stage = stage

        class Audit:
            def model_dump(self, mode="json"):
                return {
                    "lane": stage.lane,
                    "stage": stage.stage,
                    "usage": {"input_tokens": 1},
                    "execution_started": True,
                    "status": "done",
                    "input_hash": "sha256:in",
                    "output_hash": "sha256:out",
                    "trace_metadata": {},
                }

        class Result:
            final_output = {
                "is_signal": True,
                "event_type": "mention",
                "source_action": "posted",
                "subject": "token",
                "direction_hint": "bullish",
                "attention_mechanism": "direct mention",
                "impact_score": 0.5,
                "novelty_score": 0.5,
                "confidence": 0.8,
                "anchor_terms": [],
                "token_candidates": [],
                "semantic_risks": [],
                "summary_zh": "测试",
            }
            audit = Audit()

        return Result()


async def test_social_event_client_uses_agent_execution_gateway() -> None:
    gateway = FakeGateway()
    client = OpenAIAgentsSocialEventClient(model="qwen3.6", agent_gateway=gateway)

    result = await client.enrich_event(
        event={"event_id": "e1", "search_text": "hello"},
        entities=[],
        run_id="run-1",
        job={"job_id": "j1", "job_type": "watched_event", "attempt_count": 1},
    )

    assert gateway.stage.lane == "social.event_enrichment"
    assert gateway.stage.stage == "social_event"
    assert result.agent_run_audit["usage"] == {"input_tokens": 1}
```

- [ ] **Step 2: Refactor client**

`OpenAIAgentsSocialEventClient.__init__` should become:

```python
def __init__(
    self,
    *,
    model: str,
    agent_gateway: Any,
    workflow_name: str = WORKFLOW_NAME,
    max_turns: int = 1,
):
    self.model = str(model or "").strip()
    if not self.model:
        raise ValueError("llm.model is required")
    self._agent_gateway = agent_gateway
    self.workflow_name = str(workflow_name or "").strip() or WORKFLOW_NAME
    self.max_turns = max(1, min(2, int(max_turns)))
```

Remove:

- `api_key`
- `llm_gateway`
- `base_url`
- `timeout_seconds`
- `runner`
- `safety_net`
- `trace_enabled`
- `trace_include_sensitive_data`
- `_build_model`
- `_api_base`
- `_trace_id`
- `_sha256`
- direct `Agent`, `RunConfig`, `Runner`, `OpenAIChatCompletionsModel` imports.

Build `AgentStageSpec` in `enrich_event` and call:

```python
execution = await self._agent_gateway.execute(stage)
payload = payload_from_output(execution.final_output)
audit = execution.audit.model_dump(mode="json")
```

`request_audit` should build the same `AgentStageSpec` and return `self._agent_gateway.request_audit(stage)`.

- [ ] **Step 3: Update provider wiring call**

Factory should now be:

```python
return OpenAIAgentsSocialEventClient(
    model=settings.llm_model or "",
    agent_gateway=agent_gateway,
)
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/unit/integrations/openai_agents/test_social_event_agent_client.py tests/unit/test_provider_wiring_agent_execution_gateway.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add src/gmgn_twitter_intel/integrations/openai_agents/social_event_agent_client.py src/gmgn_twitter_intel/domains/social_enrichment/types/social_event_extraction.py src/gmgn_twitter_intel/domains/social_enrichment/runtime/enrichment_worker.py tests/unit/integrations/openai_agents/test_social_event_agent_client.py src/gmgn_twitter_intel/app/runtime/provider_wiring/openai.py
git commit -m "refactor: route social agent execution through gateway"
```

---

## Task 8 - Move Watchlist Prompt/Schema To Domain And Migrate Client

**Files:**

- Create: `src/gmgn_twitter_intel/domains/watchlist_intel/types/handle_summary_agent.py`
- Create: `src/gmgn_twitter_intel/domains/watchlist_intel/prompts/handle_summary.md`
- Create: `src/gmgn_twitter_intel/domains/watchlist_intel/services/handle_summary_runtime.py`
- Modify: `src/gmgn_twitter_intel/integrations/openai_agents/watchlist_summary_agent_client.py`
- Modify: `src/gmgn_twitter_intel/domains/watchlist_intel/runtime/handle_summary_worker.py`
- Modify: `src/gmgn_twitter_intel/domains/watchlist_intel/services/handle_summary_service.py`
- Create: `tests/unit/domains/watchlist_intel/test_handle_summary_runtime.py`

- [ ] **Step 1: Add Watchlist runtime tests**

Create `tests/unit/domains/watchlist_intel/test_handle_summary_runtime.py`:

```python
from __future__ import annotations

from gmgn_twitter_intel.domains.watchlist_intel.services.handle_summary_runtime import build_handle_summary_stage
from gmgn_twitter_intel.domains.watchlist_intel.types.handle_summary_agent import (
    AGENT_NAME,
    SCHEMA_VERSION,
    WatchlistHandleSummaryPayload,
)


def test_build_handle_summary_stage_is_domain_owned() -> None:
    stage = build_handle_summary_stage(
        model="qwen3.6",
        handle="alice",
        events=[{"event_id": "e1", "summary_zh": "事件"}],
        run_id="run-1",
        job={"handle": "alice", "attempt_count": 2},
        context={"window_days": 7},
    )

    assert stage.lane == "watchlist.handle_summary"
    assert stage.stage == "summary"
    assert stage.agent_name == AGENT_NAME
    assert stage.schema_version == SCHEMA_VERSION
    assert stage.output_type is WatchlistHandleSummaryPayload
    assert "alice" in stage.input_payload
```

- [ ] **Step 2: Move payload classes**

Create `types/handle_summary_agent.py`:

```python
from __future__ import annotations

from pydantic import BaseModel, Field

BACKEND = "openai_agents_sdk"
WORKFLOW_NAME = "gmgn-twitter-intel.watchlist_handle_summary"
AGENT_NAME = "WatchlistHandleSummaryAgent"
PROMPT_VERSION = "watchlist-handle-summary-v1"
SCHEMA_VERSION = "watchlist_handle_summary_v1"


class WatchlistTopicPayload(BaseModel):
    title: str
    description: str
    event_count: int = Field(ge=0)
    top_event_ids: list[str] = Field(default_factory=list)
    symbols: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)


class WatchlistHandleSummaryPayload(BaseModel):
    summary_zh: str
    topics: list[WatchlistTopicPayload] = Field(default_factory=list)
    residual_risks: list[str] = Field(default_factory=list)


__all__ = [
    "AGENT_NAME",
    "BACKEND",
    "PROMPT_VERSION",
    "SCHEMA_VERSION",
    "WORKFLOW_NAME",
    "WatchlistHandleSummaryPayload",
    "WatchlistTopicPayload",
]
```

- [ ] **Step 3: Move prompt text**

Create `prompts/handle_summary.md` with the exact current prompt text from `_instructions()` in `watchlist_summary_agent_client.py`. This is a move, not a rewrite.

- [ ] **Step 4: Add domain stage builder**

Create `services/handle_summary_runtime.py`:

```python
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from gmgn_twitter_intel.domains.watchlist_intel.types.handle_summary_agent import (
    AGENT_NAME,
    PROMPT_VERSION,
    SCHEMA_VERSION,
    WORKFLOW_NAME,
    WatchlistHandleSummaryPayload,
)
from gmgn_twitter_intel.integrations.openai_agents.agent_execution_types import AgentStageSpec


@lru_cache(maxsize=1)
def handle_summary_instructions() -> str:
    return (Path(__file__).resolve().parents[1] / "prompts" / "handle_summary.md").read_text(encoding="utf-8")


def build_handle_summary_stage(
    *,
    model: str,
    handle: str,
    events: list[dict[str, Any]],
    run_id: str,
    job: dict[str, Any],
    context: dict[str, Any],
    max_turns: int = 1,
) -> AgentStageSpec:
    input_json = {
        "handle": handle,
        "context": context,
        "events": [_event_payload(item) for item in events],
    }
    return AgentStageSpec(
        lane="watchlist.handle_summary",
        stage="summary",
        model=model,
        instructions=handle_summary_instructions(),
        input_payload=json.dumps(input_json, ensure_ascii=False, sort_keys=True),
        output_type=WatchlistHandleSummaryPayload,
        prompt_version=PROMPT_VERSION,
        schema_version=SCHEMA_VERSION,
        workflow_name=WORKFLOW_NAME,
        agent_name=AGENT_NAME,
        group_id=handle,
        trace_metadata={
            "run_id": run_id,
            "handle": handle,
            "job_handle": str(job.get("handle") or ""),
            "attempt_count": int(job.get("attempt_count") or 0),
        },
        max_turns=max_turns,
    )


def _event_payload(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_id": str(item.get("event_id") or ""),
        "received_at_ms": item.get("received_at_ms"),
        "summary_zh": str(item.get("summary_zh") or item.get("summary") or ""),
        "event_type": str(item.get("event_type") or ""),
        "symbols": item.get("symbols") or [],
        "confidence": item.get("confidence"),
    }


__all__ = ["build_handle_summary_stage", "handle_summary_instructions"]
```

During implementation, adjust `_event_payload` to match the current client payload exactly; do not keep a second payload builder in the integration client.

- [ ] **Step 5: Refactor Watchlist client**

`OpenAIAgentsWatchlistSummaryClient` should:

- accept `model` and `agent_gateway`;
- use `build_handle_summary_stage`;
- call `agent_gateway.request_audit` and `agent_gateway.execute`;
- keep `_coerce_summary_payload` only as deterministic domain post-processing if still needed;
- delete direct SDK imports and prompt/schema classes.

- [ ] **Step 6: Ensure failure path uses pre-run audit**

In `handle_summary_worker.py` / `handle_summary_service.py`, when provider call raises after a job is claimed:

- call provider `request_audit` before awaiting provider;
- pass that request audit into failure run recording;
- do not write a simplified error-only run when request audit is available.

- [ ] **Step 7: Run tests**

```bash
uv run pytest tests/unit/domains/watchlist_intel/test_handle_summary_runtime.py tests/unit/integrations/openai_agents/test_watchlist_summary_agent_client.py tests/architecture/test_agent_execution_plane_contracts.py -q
```

Expected: architecture test no longer sees Watchlist prompt/schema in integration client.

- [ ] **Step 8: Commit**

```bash
git add src/gmgn_twitter_intel/domains/watchlist_intel src/gmgn_twitter_intel/integrations/openai_agents/watchlist_summary_agent_client.py tests/unit/domains/watchlist_intel/test_handle_summary_runtime.py tests/unit/integrations/openai_agents/test_watchlist_summary_agent_client.py
git commit -m "refactor: move watchlist agent spec into domain"
```

---

## Task 9 - Migrate Narrative Client

**Files:**

- Modify: `src/gmgn_twitter_intel/integrations/openai_agents/narrative_intel_agent_client.py`
- Modify: `src/gmgn_twitter_intel/domains/narrative_intel/providers.py`
- Modify: `src/gmgn_twitter_intel/domains/narrative_intel/runtime/mention_semantics_worker.py`
- Modify: `src/gmgn_twitter_intel/domains/narrative_intel/runtime/token_discussion_digest_worker.py`
- Add/modify: `tests/unit/integrations/openai_agents/test_narrative_intel_agent_client.py`

- [ ] **Step 1: Add tests for request audit parity**

Add tests asserting both Narrative methods expose request audit before execution:

```python
async def test_narrative_label_mentions_builds_gateway_stage() -> None:
    gateway = FakeGateway()
    client = OpenAIAgentsNarrativeIntelClient(model="qwen3.6", agent_gateway=gateway)

    audit = client.request_audit_for_label_mentions(
        target={"target_type": "token", "target_id": "BTC"},
        mentions=[{"event_id": "e1", "text": "btc"}],
        run_id="run-1",
        context={"window": "1h", "scope": "all"},
    )

    assert audit["lane"] == "narrative.mention_semantics"


async def test_narrative_summarize_discussion_uses_gateway() -> None:
    gateway = FakeGateway()
    client = OpenAIAgentsNarrativeIntelClient(model="qwen3.6", agent_gateway=gateway)

    await client.summarize_discussion(
        target={"target_type": "token", "target_id": "BTC"},
        mentions=[{"event_id": "e1", "label": "bullish"}],
        run_id="run-2",
        context={"window": "1h", "scope": "all"},
    )

    assert gateway.stage.lane == "narrative.discussion_digest"
```

Use the actual method argument names from the current client when implementing the test. Keep the asserted lanes exact.

- [ ] **Step 2: Refactor Narrative client to stage specs**

Requirements:

- delete direct SDK imports;
- delete `_build_model`, `_api_base`, `_trace_id`, `_sha256`;
- preserve prompt files under `domains/narrative_intel/prompts`;
- create `AgentStageSpec` for `mention_semantics` and `discussion_digest`;
- call gateway for execution;
- top-level audit includes `usage`, `parse_mode`, `safety_net`, `input_hash`, `output_hash`;
- no audit-only compatibility write into old `trace_metadata` path.

- [ ] **Step 3: Add provider protocol request-audit parity**

If `domains/narrative_intel/providers.py` lacks request audit methods, add explicit protocol methods:

```python
def request_audit_for_label_mentions(self, **kwargs: Any) -> dict[str, Any]: ...
def request_audit_for_summarize_discussion(self, **kwargs: Any) -> dict[str, Any]: ...
```

Update workers to call the pre-run audit before awaiting provider so timeout/failure rows carry request metadata.

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/unit/integrations/openai_agents/test_narrative_intel_agent_client.py tests/unit/domains/narrative_intel -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add src/gmgn_twitter_intel/integrations/openai_agents/narrative_intel_agent_client.py src/gmgn_twitter_intel/domains/narrative_intel tests/unit/integrations/openai_agents/test_narrative_intel_agent_client.py
git commit -m "refactor: route narrative agents through execution gateway"
```

---

## Task 10 - Migrate Pulse Stage Execution

**Files:**

- Modify: `src/gmgn_twitter_intel/integrations/openai_agents/pulse_decision_agent_client.py`
- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/types/agent_decision.py`
- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_decision_runtime.py`
- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_candidate_job_service.py`
- Add/modify: `tests/unit/integrations/openai_agents/test_pulse_decision_agent_client.py`
- Add/modify: `tests/unit/pulse_lab/test_pulse_candidate_job_service.py`

- [ ] **Step 1: Add Pulse stage gateway tests**

Add tests proving:

- `evidence_debate` creates lane `pulse.evidence_debate`;
- `decision_maker` creates lane `pulse.decision_maker`;
- each stage audit retains `usage_json`, `parse_mode`, `safety_net`, `input_hash`, `output_hash`;
- `normalize_pulse_stage_output` still runs after gateway output and before final validation;
- invalid evidence ref handling remains in Pulse domain code, not gateway.

- [ ] **Step 2: Refactor Pulse client**

`OpenAIAgentsPulseDecisionClient` should:

- accept `model`, `agent_gateway`, and `decision_runtime`;
- keep `request_audit` delegating to `PulseDecisionRuntimeService`;
- build `AgentStageSpec` from each `PulseDecisionStageSpec`;
- call `agent_gateway.execute(stage_spec)` for each stage;
- convert `AgentExecutionResultAudit` into existing `StageRunAudit`;
- keep `normalize_pulse_stage_output` and evidence ref validation path exactly in Pulse code;
- delete direct `Agent`, `RunConfig`, `Runner`, `OpenAIChatCompletionsModel`, `_build_model`, `_extract_usage`, `_api_base`, `_trace_id`, `_sha256`.

- [ ] **Step 3: Preserve Pulse multi-stage semantics**

Do not collapse the pipeline. `run_decision_pipeline` remains:

```text
request audit
  -> evidence_debate stage execution
  -> domain normalization/validation
  -> decision_maker stage execution
  -> domain normalization/validation
  -> PulseDecisionResult
```

`PulseCandidateJobService` remains owner of:

- `pulse_agent_runs`;
- `pulse_agent_run_steps`;
- `pulse_evidence_packets`;
- deterministic eval;
- write gate;
- `pulse_candidates`;
- `pulse_playbook_snapshots`;
- job success/failure.

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/unit/integrations/openai_agents/test_pulse_decision_agent_client.py tests/unit/pulse_lab/test_pulse_candidate_job_service.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add src/gmgn_twitter_intel/integrations/openai_agents/pulse_decision_agent_client.py src/gmgn_twitter_intel/domains/pulse_lab tests/unit/integrations/openai_agents/test_pulse_decision_agent_client.py tests/unit/pulse_lab/test_pulse_candidate_job_service.py
git commit -m "refactor: route pulse stages through execution gateway"
```

---

## Task 11 - Reservation Before Claim For Attempt-Burning Workers

**Files:**

- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/runtime/pulse_candidate_worker.py`
- Modify: `src/gmgn_twitter_intel/domains/social_enrichment/runtime/enrichment_worker.py`
- Modify: `src/gmgn_twitter_intel/domains/watchlist_intel/runtime/handle_summary_worker.py`
- Add/modify: worker unit tests for these files.

- [ ] **Step 1: Add tests for no attempt burn on capacity denied**

For each worker with claim-on-attempt behavior, add a fake provider exposing:

```python
class FakeAgentGatewayBackpressure:
    def try_reserve(self, lane: str):
        return AgentCapacityReservation(lane=lane, acquired=False, reason=AgentExecutionErrorClass.CAPACITY_DENIED)
```

Test expectations:

- Pulse does not call `claim_due_job` when `pulse.pipeline` reservation is denied.
- Enrichment does not call `claim_next_job` when `social.event_enrichment` reservation is denied.
- Watchlist does not call `claim_next_summary_job` when `watchlist.handle_summary` reservation is denied.
- Worker result notes include `agent_backpressure_capacity_denied`.

- [ ] **Step 2: Surface gateway reservation through provider**

Keep workers insulated from integration types by adding provider-level helper methods where needed:

```python
def try_reserve_execution(self, lane: str) -> AgentCapacityReservation: ...
```

The OpenAI provider delegates to `AgentExecutionGateway.try_reserve`. Test fakes can return acquired reservations.

- [ ] **Step 3: Change run loops**

Before claim:

```python
reservation = provider.try_reserve_execution("pulse.pipeline")
if not reservation.acquired:
    return WorkerResult(processed=0, skipped=1, notes={"agent_backpressure": reservation.reason.value})
try:
    job = claim_job()
    if job is None:
        await reservation.release()
        return WorkerResult(processed=0)
    ...
finally:
    await reservation.release()
```

Use the domain lane for each worker:

- Pulse claim: `pulse.pipeline`
- Enrichment claim: `social.event_enrichment`
- Watchlist claim: `watchlist.handle_summary`

Do not add reservations to Narrative semantics unless current claim path burns attempt before provider call. Narrative can rely on provider-stage gateway execution until its queue claim semantics are changed.

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/unit/domains/pulse_lab tests/unit/domains/social_enrichment tests/unit/domains/watchlist_intel -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add src/gmgn_twitter_intel/domains/pulse_lab/runtime/pulse_candidate_worker.py src/gmgn_twitter_intel/domains/social_enrichment/runtime/enrichment_worker.py src/gmgn_twitter_intel/domains/watchlist_intel/runtime/handle_summary_worker.py tests/unit/domains
git commit -m "feat: reserve agent capacity before attempt-burning claims"
```

---

## Task 12 - Remove Old Direct Execution And Pass Architecture Tests

**Files:**

- Modify: all migrated OpenAI clients.
- Modify: `tests/architecture/test_agent_execution_plane_contracts.py`
- Modify: `tests/architecture/test_worker_runtime_contracts.py`

- [ ] **Step 1: Remove old imports**

Run:

```bash
rg -n "from agents import Agent|from agents import .*Runner|RunConfig|OpenAIChatCompletionsModel|Runner\\.run|Agent\\(" src/gmgn_twitter_intel/integrations/openai_agents
```

Expected allowed files only:

- `src/gmgn_twitter_intel/integrations/openai_agents/agent_execution_gateway.py`
- `src/gmgn_twitter_intel/integrations/openai_agents/instructor_safety_net.py`
- `src/gmgn_twitter_intel/integrations/openai_agents/agent_output_schema.py` for schema SDK primitives.

Delete every old import/call outside those files.

- [ ] **Step 2: Remove old helpers**

Run:

```bash
rg -n "def _api_base|def _trace_id|def _sha256|def _extract_usage|artifact:\\{self\\.model\\}|run_with_limits|last_worker_name|last_stage" src/gmgn_twitter_intel
```

Expected:

- no `run_with_limits`;
- no `last_worker_name`;
- no `last_stage`;
- no domain-specific OpenAI client `_api_base`, `_trace_id`, `_sha256`, `_extract_usage`;
- no `artifact:{self.model}`.

Shared hashing remains in `agent_hashing.py`.

- [ ] **Step 3: Run architecture tests**

```bash
uv run pytest tests/architecture/test_agent_execution_plane_contracts.py tests/architecture/test_worker_runtime_contracts.py -q
```

Expected: pass.

- [ ] **Step 4: Commit**

```bash
git add src/gmgn_twitter_intel tests/architecture
git commit -m "chore: remove legacy agent execution paths"
```

---

## Task 13 - Ops Status And Metrics

**Files:**

- Modify: `src/gmgn_twitter_intel/app/runtime/telemetry.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/worker_status.py`
- Modify: API status route files if they expose runtime health.
- Add/modify: unit tests for status payload.

- [ ] **Step 1: Add gateway status tests**

Add assertions that `AgentExecutionGateway.status_snapshot()` includes:

```python
{
    "global_max_concurrency": 4,
    "global_in_flight": 0,
    "lanes": {
        "pulse.decision_maker": {
            "max_concurrency": 1,
            "in_flight": 0,
            "circuit_state": "closed",
            "capacity_denied_total": 0,
            "circuit_open_total": 0,
            "timeout_total": 0,
        }
    },
}
```

- [ ] **Step 2: Add metrics counters**

Use existing Prometheus style names:

- `gmgn_agent_execution_calls_total{lane,stage,model,status,error_class}`
- `gmgn_agent_execution_seconds{lane,stage,model,status}`
- `gmgn_agent_execution_in_flight{lane,stage}`
- `gmgn_agent_execution_backpressure_total{lane,reason}`

Keep metrics in runtime/integration layer. Do not expose product readiness from these counters.

- [ ] **Step 3: Wire status snapshot into runtime status**

Expose agent execution status under an ops/runtime status field, not under product health:

```json
{
  "agent_execution": {
    "global_max_concurrency": 4,
    "lanes": {}
  }
}
```

If current status schema is strict, add optional field and update tests in the same commit.

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/unit/test_worker_status.py tests/unit/test_api_status.py tests/unit/integrations/openai_agents/test_agent_execution_gateway.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add src/gmgn_twitter_intel/app/runtime src/gmgn_twitter_intel/app/surfaces/api tests/unit
git commit -m "feat: expose agent execution ops status"
```

---

## Task 14 - Docs And Stale Spec Cleanup

**Files:**

- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/WORKERS.md`
- Modify: `docs/CONTRACTS.md`
- Modify: `docs/RELIABILITY.md`
- Modify: `docs/superpowers/specs/active/2026-05-15-worker-runtime-platform-cn.md`
- Modify: `docs/superpowers/specs/active/2026-05-19-agent-execution-plane-hard-cut-cn.md`

- [ ] **Step 1: Update architecture docs**

Document:

- `AgentExecutionGateway` owns agent execution mechanics only.
- `LLMGateway` owns OpenAI client/trace/transport only.
- Domain workers still own admission/claim/finalize.
- No central durable agent queue exists.
- Lane/circuit/backpressure status is operational, not product truth.

- [ ] **Step 2: Mark stale worker runtime spec portions**

In `2026-05-15-worker-runtime-platform-cn.md`, add a short supersession note near the top:

```markdown
**Supersession note (2026-05-19):** WorkerBase/DBPoolBundle principles remain valid, but worker inventory, DB pool count, wake connection behavior, and LLM runtime details are superseded by current runtime code and `2026-05-19-agent-execution-plane-hard-cut-cn.md`. Do not implement this spec literally where it says 12 workers, 3 DB pools, or central `LLMGateway` execution limits.
```

- [ ] **Step 3: Update owning spec status if implementation completes**

When all tasks are implemented and verified, update:

```markdown
**Status**: Implemented
```

Do not mark implemented before verification commands pass.

- [ ] **Step 4: Run docs/architecture tests**

```bash
uv run pytest tests/architecture -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add docs tests/architecture
git commit -m "docs: document agent execution plane hard cut"
```

---

## Task 15 - Full Verification

**Files:** no source edits expected.

- [ ] **Step 1: Static checks**

```bash
uv run ruff check .
```

Expected: pass.

- [ ] **Step 2: Unit tests**

```bash
uv run pytest tests/unit/test_llm_gateway.py -q
uv run pytest tests/unit/integrations/openai_agents -q
uv run pytest tests/unit/domains/narrative_intel -q
uv run pytest tests/unit/domains/pulse_lab -q
uv run pytest tests/unit/domains/social_enrichment -q
uv run pytest tests/unit/domains/watchlist_intel -q
```

Expected: pass.

- [ ] **Step 3: Architecture tests**

```bash
uv run pytest tests/architecture -q
```

Expected: pass.

- [ ] **Step 4: Integration tests**

```bash
uv run pytest tests/integration -q
```

Expected: pass in Postgres-backed environment.

- [ ] **Step 5: Runtime config validation**

```bash
uv run gmgn-twitter-intel config
```

Expected: live config paths still point to `~/.gmgn-twitter-intel/`; `workers.agent_runtime` parses if present; secrets are not printed.

- [ ] **Step 6: Boundary grep**

```bash
rg -n "run_with_limits|last_worker_name|last_stage|legacy_runner|fallback_to_old_client|agent_runtime_enabled|use_new_gateway" src tests
rg -n "Runner\\.run|Agent\\(|RunConfig\\(" src/gmgn_twitter_intel/integrations/openai_agents
rg -n "artifact:\\{self\\.model\\}|def _api_base|def _trace_id|def _sha256|def _extract_usage" src/gmgn_twitter_intel/integrations/openai_agents
```

Expected:

- first command returns no production compatibility paths;
- second command returns only gateway/safety-net/schema allowed files;
- third command returns no old duplicated helpers in domain-specific clients.

- [ ] **Step 7: Commit verification note**

```bash
git status --short
```

Expected: clean. If generated docs changed, commit them with the docs commit or explain why they are intentionally untracked.

---

## Implementation Notes

### Error mapping

Gateway-level errors map to domain behavior this way:

| Gateway error | Execution started | Domain attempt burn |
| --- | --- | --- |
| `capacity_denied` | false | no |
| `circuit_open` | false | no |
| `timeout` | true | yes |
| `rate_limited` | true if request started | yes only if started |
| `transport_error` | true if request started | yes only if started |
| `provider_error` | true | yes |
| `schema_invalid` | true | yes |

Domain validation failures remain outside gateway. Pulse invalid evidence ref, Narrative evidence mismatch, Watchlist no-input, and News deterministic rejection are domain states.

### No compatibility examples

These patterns are forbidden:

```python
if self._agent_gateway is not None:
    return await self._agent_gateway.execute(stage)
return await self._runner.run(agent, payload)
```

```python
def run_with_limits(...):
    return await self._agent_execution_gateway.execute(...)
```

```python
audit["trace_metadata"] = {**audit["trace_metadata"], **audit_extra}  # for old readers
```

Use one path, update callers/readers/tests in the same branch, and delete the old path.

### Commit discipline

Every commit should leave tests for that slice passing, but the branch is not deployable until Task 15 is complete. This lets reviewers inspect the hard cut in readable chunks without creating production mixed states.
