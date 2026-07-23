# Runtime product-AI residual hard-cut report

## Findings

- `tests/integration/test_api_health.py` still composed the retired News story-brief provider, accepted an `agent_execution_gateway`, expected a missing-LLM worker degradation reason, and published an agent-execution status snapshot.
- `tests/architecture/test_kiss_runtime_invariants.py` still required the deleted `workers.agent_runtime` policy and fixed `news.story_brief` lane.
- The original product-AI deletion guard checked only four retired files. It did not prove that the dormant model library was independently usable, provider-neutral, or unreachable from production composition.
- The first strengthened architecture run correctly found two product knowledge assets outside this task's write scope: `src/parallax/platform/agent_knowledge.py` and `src/parallax/agent_knowledge/market_research_harness.md`. Root then hard-deleted both and their isolated test; no compatibility or replacement was added.

## Scope and changes

- `tests/integration/test_api_health.py`
  - removed story-brief provider and model-gateway fixture wiring;
  - removed the retired worker's unavailable reason and agent status contract;
  - retained positive runtime-snapshot coverage through the fact-only `news_page_projection` worker;
  - added an explicit assertion that API status has no `agent_execution` business section.
- `tests/architecture/test_kiss_runtime_invariants.py`
  - removed the fixed News lane and agent-runtime-policy requirements;
  - now requires minimal dormant `llm` configuration, no `workers.agent_runtime`, and no runtime LLM composition field.
- `tests/architecture/test_product_ai_hard_delete.py`
  - verifies exact retired runtime, prompt, knowledge, provider, Search, and Token files are absent;
  - rejects any current product prompt/knowledge file, including a renamed replacement;
  - scans supported `app` and `domains` source for retired product-AI contract tokens;
  - imports every retained provider-neutral execution/capability/hash/schema/usage module and instantiates generic structured-JSON stage/policy primitives;
  - proves retained library source contains no News lane or market-research knowledge identity;
  - uses AST import/symbol inspection to prevent any production app/domain import or instantiation of the dormant library.

No API source, schemas, diagnostics, Macro, settings, or other production files were edited by this subtask.

## Verification

- `uv run pytest tests/integration/test_api_health.py -q`
  - passed: `19 passed in 27.61s`.
- `uv run pytest tests/architecture/test_product_ai_hard_delete.py tests/architecture/test_kiss_runtime_invariants.py -q`
  - passed: `15 passed in 8.11s`.
- `uv run pytest tests/architecture/test_product_ai_hard_delete.py -k dormant_llm tests/unit/integrations/model_execution -q`
  - passed: `2 passed, 52 deselected`.
- `uv run pytest tests/unit/integrations/model_execution -q`
  - passed: `50 passed in 3.51s`.
- `uv run ruff check tests/integration/test_api_health.py tests/architecture/test_kiss_runtime_invariants.py tests/architecture/test_product_ai_hard_delete.py`
  - passed.
- `git diff --check -- tests/integration/test_api_health.py tests/architecture/test_kiss_runtime_invariants.py tests/architecture/test_product_ai_hard_delete.py`
  - passed.

## Residual scan

- Supported production source is clean under the architecture scan; historical Alembic revisions remain intentionally excluded as migration evidence.
- This task's health/KISS tests contain no positive retired product-AI setup or assertion. Retired terms remain only inside the negative architecture guard.
- Outside owned scope, positive old-contract fixtures still existed at handoff in API Ops and notification integration tests: `tests/unit/test_api_ops_contract.py`, `tests/integration/test_api_http.py`, `tests/integration/test_notification_delivery.py`, `tests/integration/test_notification_worker.py`, and `tests/integration/test_notification_repository.py`. These were reported to root for their owning cleanup before the full gate.

## Risks

- The bounded runtime/architecture surface is green. Repository completion still depends on deleting the reported out-of-scope stale tests and passing the full generated/runtime/browser gates.
