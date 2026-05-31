# News Item Agent Brief Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** Active implementation in `codex/news-item-agent-brief`  
**Date:** 2026-05-20  
**Owning spec:** `docs/superpowers/specs/active/2026-05-20-news-item-agent-brief-cn.md`  
**Worktree:** `.worktrees/news-item-agent-brief/`  
**Branch:** `codex/news-item-agent-brief`

**Goal:** Add a single-news-item agent brief to `/news`: persisted Chinese summary, bull/bear view, shadow decision class, evidence refs, data gaps, and run audit, without executing agents in HTTP or frontend paths.

**Architecture:** `NewsItemBriefWorker` is the only domain writer for `news_item_agent_runs` and `news_item_agent_briefs`. It reads existing News Intel facts, builds a bounded `NewsItemBriefInputPacket`, reserves lane `news.item_brief`, and executes only through the shared `AgentExecutionGateway` via a News-domain provider contract. `/api/news`, `/api/news/items/:id`, and `/news` consume the persisted read model.

**Current code refresh:** The latest repository selection logic now treats agent admission as a front-page freshness problem, not a pure oldest-stale backlog drain. Missing current briefs are selected first; among missing briefs, newer published items win; cooled no-start backpressure retries remain eligible but sort behind never-attempted fresh items with the same publish time.

**Tech Stack:** Python 3.13, PostgreSQL/Alembic, psycopg3 repository sessions, OpenAI Agents SDK behind `AgentExecutionGateway`, FastAPI, React, TypeScript, TanStack Query, pytest, Vitest.

---

## Gateway Decision

- [x] Reuse the global agent execution plane. The News adapter is `src/parallax/integrations/openai_agents/news_item_brief_agent_client.py`; it delegates request audit, reservation, execution, trace metadata, usage, and safety-net behavior to `AgentExecutionGateway`.
- [x] Do not add a News-specific runner, SDK client, durable `agent_tasks` queue, retry scheduler, or gateway duplicate.
- [x] Keep domain ownership in the worker: candidate selection, no-start accounting, validation, run ledger writes, current brief upsert, wake emission, and page projection invalidation.
- [ ] Final verification must include a forbidden SDK scan:
  ```bash
  rg -n "from openai|import openai|agents\\.run|Runner\\.run|OpenAI\\(" src/parallax/domains/news_intel src/parallax/integrations/openai_agents/news_item_brief_agent_client.py
  ```
  Expected: no News-domain direct SDK usage; the integration adapter may import only the existing gateway types it needs.

## File Structure

### Create

- `src/parallax/platform/db/alembic/versions/20260520_0068_news_item_agent_brief.py`
- `src/parallax/domains/news_intel/types/news_item_brief.py`
- `src/parallax/domains/news_intel/prompts/news_item_brief.md`
- `src/parallax/domains/news_intel/services/news_item_brief_input.py`
- `src/parallax/domains/news_intel/services/news_item_brief_runtime.py`
- `src/parallax/domains/news_intel/services/news_item_brief_validation.py`
- `src/parallax/domains/news_intel/runtime/news_item_brief_worker.py`
- `src/parallax/integrations/openai_agents/news_item_brief_agent_client.py`
- `tests/unit/domains/news_intel/test_news_item_brief_input.py`
- `tests/unit/domains/news_intel/test_news_item_brief_runtime.py`
- `tests/unit/domains/news_intel/test_news_item_brief_types.py`
- `tests/unit/domains/news_intel/test_news_item_brief_validation.py`
- `tests/unit/domains/news_intel/test_news_item_brief_worker.py`
- `tests/unit/integrations/openai_agents/test_news_item_brief_agent_client.py`
- `tests/integration/domains/news_intel/test_news_item_agent_brief_repository.py`

### Modify

- `config.example.yaml`
- `docs/ARCHITECTURE.md`
- `docs/CONTRACTS.md`
- `docs/FRONTEND.md`
- `docs/WORKERS.md`
- `src/parallax/app/runtime/bootstrap.py`
- `src/parallax/app/runtime/provider_wiring/__init__.py`
- `src/parallax/app/runtime/provider_wiring/openai.py`
- `src/parallax/app/runtime/provider_wiring/types.py`
- `src/parallax/app/runtime/wake_bus.py`
- `src/parallax/app/runtime/worker_factories/news_intel.py`
- `src/parallax/app/runtime/worker_registry.py`
- `src/parallax/domains/news_intel/ARCHITECTURE.md`
- `src/parallax/domains/news_intel/_constants.py`
- `src/parallax/domains/news_intel/providers.py`
- `src/parallax/domains/news_intel/repositories/news_repository.py`
- `src/parallax/domains/news_intel/runtime/news_page_projection_worker.py`
- `src/parallax/domains/news_intel/services/news_page_projection.py`
- `src/parallax/platform/config/settings.py`
- `tests/architecture/test_worker_runtime_contracts.py`
- `tests/unit/test_worker_settings.py`
- `tests/unit/test_settings.py`
- `tests/unit/test_providers_wiring.py`
- `tests/unit/test_provider_wiring_agent_execution_gateway.py`
- `tests/unit/test_bootstrap_worker_runtime_wiring.py`
- `tests/unit/test_api_news_contract.py`
- `tests/unit/domains/news_intel/test_news_page_projection.py`
- `tests/unit/domains/news_intel/test_news_workers.py`
- `tests/integration/domains/news_intel/test_news_repository.py`
- `web/src/shared/model/newsIntel.ts`
- `web/src/lib/api/client.ts`
- `web/src/features/news/NewsPage.tsx`
- `web/src/features/news/newsViewModel.ts`
- `web/src/features/news/news.css`
- `web/tests/component/features/news/NewsPage.test.tsx`
- `web/tests/unit/features/news/useNewsPage.test.ts`

## Task 1: Config, Registry, And Gateway Guardrails

- [x] Add `llm.news_item_brief_model`, worker key `news_item_brief`, wake channel `news_item_brief_updated`, and agent lane `news.item_brief`.
- [x] Wire `NewsItemBriefProvider` through `provider_wiring/openai.py` using the existing `AgentExecutionGateway`.
- [x] Add tests proving unknown lane keys still fail and bootstrap wires News only when News Intel, LLM, and the worker are enabled.
- [x] Run:
  ```bash
  uv run pytest tests/unit/test_worker_settings.py tests/unit/test_settings.py tests/unit/test_providers_wiring.py tests/unit/test_provider_wiring_agent_execution_gateway.py tests/unit/test_bootstrap_worker_runtime_wiring.py -q
  ```
  Expected: all selected tests pass.

## Task 2: Storage And Repository

- [x] Create `news_item_agent_runs` as append-only audit ledger and `news_item_agent_briefs` as current item-scoped read model.
- [x] Add compact brief columns to `news_page_rows` with default `{"status":"pending"}`.
- [x] Implement repository methods for run insert, current upsert/get, stale candidate selection, page projection joins, and detail hydration.
- [x] Ensure no-start backpressure rows use `execution_started=false` and do not count against provider attempts.
- [x] Update `list_items_for_brief` ordering so missing briefs feed the front page first: `missing_current_brief DESC`, `published_at_ms DESC`, cooled backpressure retries after clean/fresh candidates, then `source_updated_at_ms DESC`.
- [x] Add repository regression coverage for newest-missing-brief priority and cooled-backpressure retry deprioritization.
- [x] Run:
  ```bash
  uv run pytest tests/integration/domains/news_intel/test_news_item_agent_brief_repository.py tests/integration/domains/news_intel/test_news_repository.py -q
  ```
  Expected: repository integration tests pass against local PostgreSQL.
  Current refresh note: rerun is still required after the latest candidate-ordering change in the main checkout.

## Task 3: Typed Packet, Prompt, And Validator

- [x] Define strict Pydantic input/output models with bounded lengths and enum fields.
- [x] Build `NewsItemBriefInputPacket` from item, story, token lanes, fact lanes, and allowed evidence refs.
- [x] Validate output: evidence refs must exist in packet, execution language fails, unsupported assets downgrade or fail, `ready` and `insufficient` invariants are enforced.
- [x] Run:
  ```bash
  uv run pytest tests/unit/domains/news_intel/test_news_item_brief_input.py tests/unit/domains/news_intel/test_news_item_brief_types.py tests/unit/domains/news_intel/test_news_item_brief_validation.py tests/unit/domains/news_intel/test_news_item_brief_runtime.py -q
  ```
  Expected: strict schema and validator tests pass.

## Task 4: OpenAI Adapter Through Shared Gateway

- [x] Implement `NewsItemBriefAgentClient` as the only concrete provider adapter.
- [x] Use gateway request audit, reservation, typed execution, result audit, and trace metadata; do not call OpenAI Agents SDK directly from the domain.
- [x] Add integration-adapter unit tests for schema, audit metadata, reservation, and validation result propagation.
- [x] Run:
  ```bash
  uv run pytest tests/unit/integrations/openai_agents/test_news_item_brief_agent_client.py -q
  ```
  Expected: adapter tests pass.

## Task 5: Worker Execution And Backpressure

- [x] Implement `NewsItemBriefWorker` with bounded batch selection, advisory lock, wake input, no DB session held during provider work, and reservation release.
- [x] Write succeeded, validation-failed, provider-failed, audit-failed, and no-start backpressure ledger behavior.
- [x] Emit `news_item_brief_updated` only when current brief state changes.
- [x] Run:
  ```bash
  uv run pytest tests/unit/domains/news_intel/test_news_item_brief_worker.py tests/unit/test_bootstrap_worker_runtime_wiring.py -q
  ```
  Expected: worker and bootstrap tests pass.

## Task 6: API And Page Projection

- [x] Join current brief into page projection source queries.
- [x] Include compact `agent_brief`, `agent_brief_status`, and `agent_brief_computed_at_ms` in `news_page_rows`.
- [x] Include full current brief plus sanitized latest run summary in item detail.
- [x] Reproject rows when the current brief updates.
- [x] Run:
  ```bash
  uv run pytest tests/unit/domains/news_intel/test_news_page_projection.py tests/unit/domains/news_intel/test_news_workers.py tests/unit/test_api_news_contract.py -q
  uv run pytest tests/integration/domains/news_intel/test_news_repository.py tests/integration/domains/news_intel/test_news_item_agent_brief_repository.py -q
  ```
  Expected: API and projection tests pass.

## Task 7: Frontend `/news`

- [x] Replace generated event question, route, and next-action narrative with persisted brief columns: `Brief`, `Direction`, `Decision`, `Evidence/Gaps`.
- [x] Add detail `Agent brief` panel with Chinese summary, market read, bull/bear, watch triggers, invalidation, data gaps, evidence refs, and audit metadata.
- [x] Keep `newsViewModel.ts` to mechanical helpers only; do not derive summary, market read, bull/bear, decision, or next action from headline keywords.
- [x] Add AC8 regression: changing only headline does not change rendered analysis.
- [x] Add structured data-gap regression for `{description_zh, severity}` full brief payloads.
- [ ] Run:
  ```bash
  cd web
  npm test -- --run tests/component/features/news/NewsPage.test.tsx tests/unit/features/news/useNewsPage.test.ts
  npm run typecheck
  ```
  Expected: frontend tests and typecheck pass.

## Task 8: Docs And Contracts

- [ ] Update `docs/ARCHITECTURE.md`: single writer, agent execution plane, and News domain ownership.
- [ ] Update `src/parallax/domains/news_intel/ARCHITECTURE.md`: stage map and read-model ownership.
- [ ] Update `docs/WORKERS.md`: worker inventory, wake channels, `news.item_brief` lane, and no-start semantics.
- [ ] Update `docs/CONTRACTS.md`: config keys and `/api/news` agent brief response contract.
- [ ] Update `docs/FRONTEND.md`: `/news` consumes persisted agent brief and must not recreate narrative locally.

## Task 9: Final Verification And Review

- [ ] Run backend targeted suites:
  ```bash
  uv run pytest tests/unit/domains/news_intel/test_news_item_brief_input.py tests/unit/domains/news_intel/test_news_item_brief_runtime.py tests/unit/domains/news_intel/test_news_item_brief_types.py tests/unit/domains/news_intel/test_news_item_brief_validation.py tests/unit/domains/news_intel/test_news_item_brief_worker.py tests/unit/integrations/openai_agents/test_news_item_brief_agent_client.py -q
  uv run pytest tests/unit/domains/news_intel/test_news_page_projection.py tests/unit/domains/news_intel/test_news_workers.py tests/unit/test_api_news_contract.py tests/unit/test_bootstrap_worker_runtime_wiring.py tests/unit/test_provider_wiring_agent_execution_gateway.py tests/unit/test_providers_wiring.py tests/unit/test_settings.py tests/unit/test_worker_settings.py tests/architecture/test_worker_runtime_contracts.py -q
  uv run pytest tests/integration/domains/news_intel/test_news_repository.py tests/integration/domains/news_intel/test_news_item_agent_brief_repository.py -q
  ```
  Expected: all selected pytest suites pass.
- [ ] Specifically verify latest admission-ordering ACs:
  ```bash
  uv run pytest \
    tests/integration/domains/news_intel/test_news_item_agent_brief_repository.py::test_list_items_for_brief_prioritizes_newest_missing_briefs_for_front_page \
    tests/integration/domains/news_intel/test_news_item_agent_brief_repository.py::test_list_items_for_brief_deprioritizes_cooled_backpressure_retry_for_same_publish_time \
    -q
  ```
  Expected: newest missing briefs outrank old missing briefs; never-attempted fresh items outrank cooled no-start backpressure retries at the same publish time.
- [ ] Run frontend targeted suites:
  ```bash
  cd web
  npm test -- --run tests/component/features/news/NewsPage.test.tsx tests/unit/features/news/useNewsPage.test.ts
  npm run typecheck
  ```
  Expected: all selected Vitest tests and TypeScript check pass.
- [ ] Run browser/manual UI check for `http://localhost:8765/news` when the local server is available. Expected: list/detail render without overlapping text, failed API requests, or heuristic trading narrative.
- [ ] Run:
  ```bash
  git diff --check
  ```
  Expected: no whitespace errors.
- [ ] Dispatch final code reviewer subagent for full implementation before marking this plan complete.
