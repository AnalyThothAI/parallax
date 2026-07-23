# Task 5 Config/CLI hard-cut report

## Findings

- `WorkersSettings` still owned two retired product-AI control planes: the flat `agent_runtime` policy and the `news_story_brief` worker block.
- `Settings` still derived production readiness through `llm_configured` and `news_agent_execution_enabled`.
- `NotificationsConfig` still admitted the retired `news_high_signal` rule and three query-policy knobs.
- `parallax config` still published an `agent_execution` status object containing model, provider family, backend, base URL, and configured state.
- The provider-neutral dormant `llm` object already has the intended strict surface: only `api_key` and `base_url`.

## Scope and changes

- `src/parallax/platform/config/settings.py`
  - removed the `AgentRuntimePolicy` production-config import;
  - removed `workers.agent_runtime`;
  - removed `NewsStoryBriefWorkerSettings` and `workers.news_story_brief`;
  - removed `llm_configured` and `news_agent_execution_enabled`;
  - removed the `news_high_signal` rule ID, default rule, default YAML, and all three query-policy fields;
  - retained both watched-account notification rules and the provider-neutral dormant `llm` config.
- `src/parallax/app/surfaces/cli/commands/config.py`
  - removed the complete `agent_execution` status payload; no model/provider/backend/base-URL status is exposed.
- `tests/unit/test_settings.py`
  - deleted retired agent-runtime and story-brief behavior tests;
  - added positive assertions for the two watched-account rules;
  - asserted that retired worker/status properties are absent;
  - asserted strict rejection of retired `news_high_signal` configuration;
  - retained validation of the strict dormant `llm` schema and asserted it is absent from CLI status.
- `tests/unit/test_worker_factories.py`
  - deleted the obsolete story-brief worker composition test.
- `config.example.yaml` required no edit: it contains only the strict dormant `llm.api_key/base_url` object and no retired notification or worker surface.

## Verification

- `uv run pytest tests/unit/test_settings.py tests/unit/test_worker_factories.py -q`
  - passed: `65 passed`.
- `uv run pytest tests/unit/test_settings.py tests/unit/test_worker_factories.py tests/architecture/test_product_ai_hard_delete.py -q`
  - passed: `66 passed`.
- `uv run ruff check src/parallax/platform/config/settings.py src/parallax/app/surfaces/cli/commands/config.py tests/unit/test_settings.py tests/unit/test_worker_factories.py`
  - passed.
- `git diff --check -- src/parallax/platform/config/settings.py src/parallax/app/surfaces/cli/commands/config.py tests/unit/test_settings.py tests/unit/test_worker_factories.py`
  - passed.

## Consumers outside owned scope

- `src/parallax/app/operations/diagnostics.py:652` still reads deleted `settings.llm_configured`; the same module still builds the retired runtime `agent_execution` diagnostics section.
- `src/parallax/app/surfaces/api/routes_notifications.py:176` still special-cases `news_high_signal`.
- `tests/architecture/test_kiss_runtime_invariants.py` still imports/tests the retired worker-owned agent-runtime contract.
- `tests/unit/test_worker_settings.py` still tests `agent_runtime` and `news_story_brief`; a focused audit produced eight expected failures from those removed fields.
- `tests/unit/test_ops_diagnostics.py` still tests story-brief and agent-execution diagnostics; a focused audit exposed the deleted `llm_configured` reference plus obsolete agent-execution/story-worker assertions.
- `tests/unit/test_run_worker_once.py` still filters an `agent_runtime` pseudo-worker key.
- `tests/unit/test_provider_wiring_agent_execution_gateway.py`, `tests/unit/test_providers_wiring.py`, and `tests/integration/test_cli.py` still construct retired worker config.
- Notification API/integration/unit tests still contain `news_high_signal` fixtures and contract assertions; migration cleanup fixtures are intentional and should remain.
- Health, runtime snapshot, queue-health, telemetry, and diagnostics tests still contain the retired `news_story_brief` worker/lane.

## Risks

- The focused owned surface is green, but the full suite cannot be green until the listed runtime diagnostics/API consumers and obsolete tests are hard-deleted by their owning tasks.
- Existing operator `workers.yaml` files containing `agent_runtime` or `news_story_brief`, and `config.yaml` files containing `news_high_signal`, now fail closed under strict Pydantic validation. This is the intended no-compatibility hard cut.
