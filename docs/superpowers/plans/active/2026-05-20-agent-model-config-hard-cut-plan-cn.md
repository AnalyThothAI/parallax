# Agent Model Config Hard Cut Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move all LLM model selection out of `config.yaml` and into `workers.yaml -> agent_runtime`, with no runtime compatibility aliases for old model fields.

**Architecture:** `config.yaml` owns provider transport and secrets only; `workers.yaml` owns worker runtime and agent execution policy. Domain clients build prompt/schema/input stage specs, while `AgentExecutionGateway` resolves the effective model from `agent_runtime.defaults` plus lane overrides and writes that model into the audit envelope.

**Tech Stack:** Python 3.12, Pydantic settings, OpenAI Agents SDK, pytest, existing `WorkerBase` / `AgentExecutionGateway` runtime.

---

## File Structure

- Modify `src/gmgn_twitter_intel/platform/config/settings.py`: remove legacy `llm.model` and domain-specific model overrides; add `AgentRuntimeDefaultsSettings` and lane-level `model`; update config helpers and default YAML.
- Modify `src/gmgn_twitter_intel/platform/agent_execution.py`: make `AgentStageSpec` no longer caller-owned for model selection and let audit construction receive resolved model from gateway.
- Modify `src/gmgn_twitter_intel/integrations/openai_agents/agent_execution_gateway.py`: resolve model from lane policy, build model clients from the resolved model, and include resolved model in audit/status.
- Modify `src/gmgn_twitter_intel/app/runtime/provider_wiring/openai.py`: stop reading model fields from `Settings.llm`; build provider clients without model arguments and let their stages rely on lane policy.
- Modify OpenAI adapter clients under `src/gmgn_twitter_intel/integrations/openai_agents/`: remove constructor model requirements and artifact model precomputation that duplicates gateway policy.
- Modify domain stage builders under `src/gmgn_twitter_intel/domains/{news_intel,watchlist_intel,pulse_lab}/services/`: remove `model=` from `AgentStageSpec` construction.
- Modify CLI config output in `src/gmgn_twitter_intel/app/surfaces/cli/commands/config.py`: report model policy under `workers.agent_runtime`, not `enrichment.model`.
- Modify docs `docs/CONTRACTS.md`, `docs/WORKERS.md`, and `docs/ARCHITECTURE.md`: state that model selection belongs only to `workers.yaml -> agent_runtime`.
- Modify tests in `tests/unit/test_settings.py`, `tests/unit/test_worker_settings.py`, `tests/unit/test_provider_wiring_agent_execution_gateway.py`, `tests/unit/integrations/openai_agents/`, and architecture tests to enforce the hard cut.

## Tasks

### Task 1: Lock The New Config Contract With Failing Tests

**Files:**
- Modify: `tests/unit/test_settings.py`
- Modify: `tests/unit/test_worker_settings.py`
- Modify: `tests/architecture/test_agent_execution_plane_contracts.py`

- [ ] **Step 1: Write failing settings tests**

Add tests that:

```python
def test_load_settings_rejects_legacy_llm_model_fields(tmp_path, monkeypatch):
    home = _write_config(tmp_path, monkeypatch)
    payload = yaml.safe_load((home / "config.yaml").read_text())
    payload["llm"]["model"] = "gpt-old"
    (home / "config.yaml").write_text(yaml.safe_dump(payload), encoding="utf-8")

    with pytest.raises(ValidationError):
        load_settings(require_ws_token=False)
```

and equivalent cases for `pulse_agent_model`, `watchlist_handle_summary_model`, `narrative_intel_model`, and `news_item_brief_model`.

- [ ] **Step 2: Write failing worker model policy tests**

Add tests that:

```python
settings = WorkersSettings(
    agent_runtime={
        "defaults": {"model": "qwen3.6"},
        "lanes": {"news.item_brief": {"model": "qwen3.6-fast"}}
    }
)
assert settings.agent_runtime.defaults.model == "qwen3.6"
assert settings.agent_runtime.lanes["news.item_brief"].model == "qwen3.6-fast"
assert settings.agent_runtime.lanes["pulse.pipeline"].model is None
```

- [ ] **Step 3: Write architecture guard**

Add a static assertion that `LlmConfig.model_fields` does not contain `model`, `pulse_agent_model`, `watchlist_handle_summary_model`, `narrative_intel_model`, or `news_item_brief_model`, and that production code does not reference `settings.pulse_agent_model`, `settings.narrative_intel_model`, `settings.watchlist_handle_summary_model`, or `settings.news_item_brief_model`.

- [ ] **Step 4: Run the red tests**

Run:

```bash
uv run pytest tests/unit/test_settings.py tests/unit/test_worker_settings.py tests/architecture/test_agent_execution_plane_contracts.py -q
```

Expected: failures showing the old fields still exist and `agent_runtime.defaults.model` is not implemented.

### Task 2: Move Model Policy Into WorkersSettings

**Files:**
- Modify: `src/gmgn_twitter_intel/platform/config/settings.py`
- Modify: `src/gmgn_twitter_intel/app/surfaces/cli/commands/config.py`

- [ ] **Step 1: Add model policy schema**

Add:

```python
class AgentRuntimeDefaultsSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str
    max_turns: int = Field(default=1, ge=1)
    disable_thinking: bool = True
    include_usage: bool = True
```

Then add `defaults: AgentRuntimeDefaultsSettings` to `AgentRuntimeSettings`, and `model: str | None = None` to `AgentLaneSettings`.

- [ ] **Step 2: Remove legacy model fields from LlmConfig**

Delete `model`, `pulse_agent_model`, `watchlist_handle_summary_model`, `narrative_intel_model`, and `news_item_brief_model` from `LlmConfig` and from the optional-string validator.

- [ ] **Step 3: Replace model configured properties**

Keep boolean readiness properties but make them depend on `settings.llm_api_key` and `settings.workers.agent_runtime.defaults.model`. Remove properties that expose legacy model names.

- [ ] **Step 4: Update default YAML**

Remove model fields from `default_config_yaml()`. Add:

```yaml
agent_runtime:
  defaults:
    model: "qwen3.6"
    max_turns: 1
    disable_thinking: true
    include_usage: true
```

to `default_workers_yaml()` before global concurrency fields.

- [ ] **Step 5: Update CLI config output**

Remove `data.enrichment.model`; keep `data.enrichment.llm_configured`, provider, base URL, and trace booleans.

- [ ] **Step 6: Run settings tests**

Run:

```bash
uv run pytest tests/unit/test_settings.py tests/unit/test_worker_settings.py -q
```

Expected: pass after test updates and implementation.

### Task 3: Resolve Models Inside AgentExecutionGateway

**Files:**
- Modify: `src/gmgn_twitter_intel/platform/agent_execution.py`
- Modify: `src/gmgn_twitter_intel/integrations/openai_agents/agent_execution_gateway.py`
- Modify: `tests/unit/integrations/openai_agents/test_agent_execution_gateway.py`
- Modify: `tests/unit/integrations/openai_agents/test_agent_execution_audit.py`

- [ ] **Step 1: Write failing gateway test**

Add a test where the stage has lane `news.item_brief`, `agent_runtime.defaults.model` is `qwen3.6`, lane model is `qwen3.6-fast`, and `llm_gateway.openai_client_calls[0]["model"] == "qwen3.6-fast"`.

- [ ] **Step 2: Remove caller-owned model from AgentStageSpec**

Delete the required `model` field from `AgentStageSpec`. Add a helper on the gateway:

```python
def _stage_model(self, stage: AgentStageSpec) -> str:
    lane_policy = self._lane_state(stage.lane).policy
    return str(lane_policy.model or self._policy.defaults.model).strip()
```

- [ ] **Step 3: Build audit with resolved model**

Change `request_audit(stage)` to resolve model first and pass it into `AgentExecutionRequestAudit.from_stage(...)`.

- [ ] **Step 4: Build model client with resolved model**

Change `_run_stage()` to call `_model_for(resolved_model, timeout_s=...)`.

- [ ] **Step 5: Run gateway tests**

Run:

```bash
uv run pytest tests/unit/integrations/openai_agents/test_agent_execution_gateway.py tests/unit/integrations/openai_agents/test_agent_execution_audit.py -q
```

Expected: pass, with audit model matching resolved lane/default policy.

### Task 4: Remove Model Duplication From OpenAI Adapters

**Files:**
- Modify: `src/gmgn_twitter_intel/app/runtime/provider_wiring/openai.py`
- Modify: `src/gmgn_twitter_intel/integrations/openai_agents/pulse_decision_agent_client.py`
- Modify: `src/gmgn_twitter_intel/integrations/openai_agents/narrative_intel_agent_client.py`
- Modify: `src/gmgn_twitter_intel/integrations/openai_agents/social_event_agent_client.py`
- Modify: `src/gmgn_twitter_intel/integrations/openai_agents/watchlist_summary_agent_client.py`
- Modify: `src/gmgn_twitter_intel/integrations/openai_agents/news_item_brief_agent_client.py`
- Modify: `src/gmgn_twitter_intel/domains/news_intel/services/news_item_brief_runtime.py`
- Modify: `src/gmgn_twitter_intel/domains/watchlist_intel/services/handle_summary_runtime.py`
- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_decision_runtime.py`

- [ ] **Step 1: Remove constructor model parameters**

OpenAI adapter constructors should accept `agent_gateway` and domain runtime dependencies only. They should expose `model` only as a diagnostic property backed by the gateway policy for their primary lane when needed by existing repositories.

- [ ] **Step 2: Remove `model=` from AgentStageSpec construction**

Each stage builder should pass lane, stage, instructions, input, output type, prompt/schema versions, workflow, agent name, group id, trace metadata, max turns, and tools only.

- [ ] **Step 3: Move artifact hash model source to audit**

Where adapters need artifact hashes before execution, use `agent_gateway.request_audit(stage)["artifact_version_hash"]` instead of recomputing from a local model field.

- [ ] **Step 4: Update provider wiring**

Delete calls to `settings.llm_model`, `settings.pulse_agent_model`, `settings.narrative_intel_model`, `settings.watchlist_handle_summary_model`, and `settings.news_item_brief_model`.

- [ ] **Step 5: Run adapter tests**

Run:

```bash
uv run pytest tests/unit/test_provider_wiring_agent_execution_gateway.py tests/unit/test_social_event_agent_client.py tests/unit/test_watchlist_summary_agent_client.py tests/unit/test_narrative_intel_agent_client.py tests/unit/integrations/openai_agents/test_news_item_brief_agent_client.py -q
```

Expected: pass with stages no longer carrying caller-selected models.

### Task 5: Update Runtime Wiring And Config Defaults

**Files:**
- Modify: `src/gmgn_twitter_intel/app/runtime/providers_wiring.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/app.py` if readiness checks refer to old properties.
- Modify: `tests/unit/test_bootstrap_worker_runtime_wiring.py`
- Modify: `tests/unit/test_providers_wiring.py`
- Modify: `tests/integration/test_api_health.py`

- [ ] **Step 1: Replace configured checks**

Make all LLM-backed configured checks use the new `agent_runtime.defaults.model` plus `llm.api_key`.

- [ ] **Step 2: Update tests to provide model policy in workers**

Replace old fixture payloads such as:

```python
llm={"api_key": "sk-test", "pulse_agent_model": "gpt-pulse"}
```

with:

```python
llm={"api_key": "sk-test"}
workers={"agent_runtime": {"defaults": {"model": "gpt-pulse"}}}
```

and use lane model overrides where tests need domain-specific model names.

- [ ] **Step 3: Run runtime wiring tests**

Run:

```bash
uv run pytest tests/unit/test_bootstrap_worker_runtime_wiring.py tests/unit/test_providers_wiring.py tests/integration/test_api_health.py -q
```

Expected: pass.

### Task 6: Update Docs And Hard-Cut Guards

**Files:**
- Modify: `docs/CONTRACTS.md`
- Modify: `docs/WORKERS.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `tests/architecture/test_worker_runtime_contracts.py`
- Modify: `tests/architecture/test_src_domain_architecture.py`

- [ ] **Step 1: Document config ownership**

State that `config.yaml llm` owns provider/base URL/API key/tracing only, and `workers.yaml agent_runtime.defaults/lanes` owns model selection and execution policy.

- [ ] **Step 2: Add static forbidden-reference checks**

Reject production references to the deleted legacy model settings and reject `model=` in `AgentStageSpec(...)` calls outside tests that deliberately construct stage specs.

- [ ] **Step 3: Run architecture tests**

Run:

```bash
uv run pytest tests/architecture/test_agent_execution_plane_contracts.py tests/architecture/test_worker_runtime_contracts.py tests/architecture/test_src_domain_architecture.py -q
```

Expected: pass.

### Task 7: Final Verification

**Files:**
- No new production files.

- [ ] **Step 1: Run focused backend suite**

Run:

```bash
uv run pytest tests/unit/test_settings.py tests/unit/test_worker_settings.py tests/unit/integrations/openai_agents tests/unit/test_provider_wiring_agent_execution_gateway.py -q
```

Expected: pass.

- [ ] **Step 2: Run architecture suite**

Run:

```bash
uv run pytest tests/architecture -q
```

Expected: pass.

- [ ] **Step 3: Run compile check**

Run:

```bash
uv run python -m compileall src/gmgn_twitter_intel tests
```

Expected: completes without syntax errors.

- [ ] **Step 4: Confirm runtime config surface**

Run:

```bash
uv run gmgn-twitter-intel config
```

Expected: output contains `workers.agent_runtime.defaults.model`, contains lane model overrides when configured, and does not contain `llm.model` or old domain-specific LLM model fields.

## Self-Review

- Spec coverage: plan covers schema, default config, gateway model resolution, provider/client duplication removal, docs, architecture guards, and verification.
- Placeholder scan: no `TBD`, `TODO`, or unspecified test command remains.
- Type consistency: `agent_runtime.defaults.model` is the only required default model; lane `model` is optional and falls back to that default.
