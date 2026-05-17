# Agent Harness Closed Loop Phase 0c Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 Signal Pulse agent runtime 从“可回放 stage runner”升级成闭环 harness 系统：每次 run 绑定版本化 harness manifest，并自动生成 deterministic eval case / eval result，形成 trace -> eval -> regression gate 的最小生产闭环。

**Architecture:** `pulse_lab` 继续拥有 harness manifest、eval case、deterministic grader 与持久化契约；`integrations/openai_agents` 只消费 harness metadata 并写入 Agents SDK trace metadata；`PulseCandidateWorker` 在每个 run 开始前 upsert harness version，在 run 完成后写 eval case/result。PostgreSQL 仍是唯一 ledger，不引入 Promptfoo/HALO/Langfuse 运行时依赖。

**Tech Stack:** Python 3.12, PostgreSQL, Alembic, Pydantic/dataclasses, OpenAI Agents SDK, pytest, ruff.

---

## Status

**Status:** Ready for inline execution
**Date:** 2026-05-14
**Worktree:** `.worktrees/unified-agent-runtime-phase-0b/`
**Branch:** `codex/unified-agent-runtime-phase-0b`
**Parent plan:** `docs/superpowers/plans/active/2026-05-14-unified-agent-runtime-phase-0b-plan-cn.md`

## Scope

Phase 0c 只做闭环地基，不把真实外部工具接进 agent。

- Add versioned harness manifest ledger.
- Add run-level `runtime_version` / `runtime_hash`.
- Add deterministic eval case/result ledger.
- Generate one eval case/result per completed Pulse run.
- Keep hard-cut semantics: no old recommendation payload, no legacy aliases, no dual-read compatibility path.

## File Structure

| File | Responsibility |
|---|---|
| `src/gmgn_twitter_intel/platform/db/alembic/versions/20260514_0038_agent_runtime_closed_loop.py` | Add harness/eval tables and run harness columns. |
| `src/gmgn_twitter_intel/domains/pulse_lab/services/agent_runtime.py` | Build stable Pulse harness manifest and hash. |
| `src/gmgn_twitter_intel/domains/pulse_lab/services/agent_eval.py` | Build deterministic eval cases and grade them. |
| `src/gmgn_twitter_intel/domains/pulse_lab/repositories/pulse_repository.py` | Persist harness versions, eval cases, eval results, and run harness fields. |
| `src/gmgn_twitter_intel/domains/pulse_lab/providers.py` | Hard-cut provider protocol to require harness metadata. |
| `src/gmgn_twitter_intel/app/runtime/providers_wiring.py` | Pass harness metadata through the OpenAI provider adapter. |
| `src/gmgn_twitter_intel/integrations/openai_agents/pulse_decision_agent_client.py` | Include harness metadata in request audit and trace metadata. |
| `src/gmgn_twitter_intel/domains/pulse_lab/runtime/pulse_candidate_worker.py` | Build/upsert harness before run; write eval case/result after run. |
| `tests/unit/test_pulse_agent_runtime.py` | Unit coverage for manifest stability and deterministic grader. |
| `tests/integration/test_pulse_repository.py` | Repository round-trip coverage for harness/eval ledger. |
| `tests/e2e/test_pulse_agent_runtime_flow.py` | E2E assertion that real worker path writes harness/eval data. |

## Task 1: Harness Manifest And Storage Ledger

**Files:**
- Create: `src/gmgn_twitter_intel/platform/db/alembic/versions/20260514_0038_agent_runtime_closed_loop.py`
- Create: `src/gmgn_twitter_intel/domains/pulse_lab/services/agent_runtime.py`
- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/repositories/pulse_repository.py`
- Test: `tests/unit/test_pulse_agent_runtime.py`
- Test: `tests/integration/test_pulse_repository.py`

- [ ] **Step 1: Write failing tests**
  - `test_pulse_harness_manifest_hash_is_stable_and_model_sensitive`
  - `test_agent_runtime_version_round_trip`
  - `test_insert_agent_run_stores_harness_identity`

- [ ] **Step 2: Verify RED**
  ```bash
  uv run pytest tests/unit/test_pulse_agent_runtime.py tests/integration/test_pulse_repository.py::test_agent_runtime_version_round_trip tests/integration/test_pulse_repository.py::test_insert_agent_run_stores_harness_identity -q
  ```
  Expected: fails because `agent_runtime.py` and repository methods/columns do not exist.

- [ ] **Step 3: Implement minimal GREEN**
  - Add `pulse_agent_runtime_versions`.
  - Add `runtime_version` and `runtime_hash` to `pulse_agent_runs`.
  - Add `build_pulse_runtime_manifest(...)` and `pulse_runtime_hash(...)`.
  - Add repository `upsert_agent_runtime_version(...)`, `agent_runtime_version(...)`.
  - Extend `insert_agent_run(...)` with required harness fields.

- [ ] **Step 4: Verify GREEN**
  ```bash
  uv run pytest tests/unit/test_pulse_agent_runtime.py tests/integration/test_pulse_repository.py::test_agent_runtime_version_round_trip tests/integration/test_pulse_repository.py::test_insert_agent_run_stores_harness_identity -q
  ```

## Task 2: Deterministic Eval Case And Result Ledger

**Files:**
- Modify: `src/gmgn_twitter_intel/platform/db/alembic/versions/20260514_0038_agent_runtime_closed_loop.py`
- Create: `src/gmgn_twitter_intel/domains/pulse_lab/services/agent_eval.py`
- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/repositories/pulse_repository.py`
- Test: `tests/unit/test_pulse_agent_runtime.py`
- Test: `tests/integration/test_pulse_repository.py`

- [ ] **Step 1: Write failing tests**
  - `test_deterministic_eval_flags_critic_ceiling_violation`
  - `test_deterministic_eval_passes_valid_three_stage_decision`
  - `test_agent_eval_case_and_result_round_trip`

- [ ] **Step 2: Verify RED**
  ```bash
  uv run pytest tests/unit/test_pulse_agent_runtime.py tests/integration/test_pulse_repository.py::test_agent_eval_case_and_result_round_trip -q
  ```
  Expected: fails because eval service and repository methods/tables do not exist.

- [ ] **Step 3: Implement minimal GREEN**
  - Add `pulse_agent_eval_cases`.
  - Add `pulse_agent_eval_results`.
  - Add repository `insert_agent_eval_case(...)`, `list_agent_eval_cases(...)`, `upsert_agent_eval_result(...)`, `list_agent_eval_results(...)`.
  - Add deterministic grader checks:
    - final route/recommendation match the run response.
    - `critic.confidence_ceiling` is not exceeded by judge/final confidence.
    - non-abstain decisions have evidence ids or residual risks.
    - hard-blocked completeness uses `research_only_gate` and `abstain`.
    - source_seed context never produces CEX/Meme asset route.
    - trading execution language is absent.

- [ ] **Step 4: Verify GREEN**
  ```bash
  uv run pytest tests/unit/test_pulse_agent_runtime.py tests/integration/test_pulse_repository.py::test_agent_eval_case_and_result_round_trip -q
  ```

## Task 3: Worker Runtime Closed Loop

**Files:**
- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/providers.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/providers_wiring.py`
- Modify: `src/gmgn_twitter_intel/integrations/openai_agents/pulse_decision_agent_client.py`
- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/runtime/pulse_candidate_worker.py`
- Modify tests: `tests/unit/test_pulse_candidate_worker.py`
- Modify tests: `tests/e2e/test_pulse_agent_runtime_flow.py`

- [ ] **Step 1: Write failing runtime tests**
  - E2E asserts run has `runtime_version`, `runtime_hash`.
  - E2E asserts one harness version row exists.
  - E2E asserts one eval case and one passing eval result exist for the run.
  - Unit fake provider signature requires `harness`.

- [ ] **Step 2: Verify RED**
  ```bash
  uv run pytest tests/e2e/test_pulse_agent_runtime_flow.py tests/unit/test_pulse_candidate_worker.py -q
  ```
  Expected: fails because runtime does not build or persist harness/eval data.

- [ ] **Step 3: Implement minimal GREEN**
  - Worker builds harness manifest from provider/model/prompt/schema/stage/gate policy.
  - Worker calls `repos.pulse.upsert_agent_runtime_version(...)` before `insert_agent_run(...)`.
  - Worker passes `harness` to `request_audit(...)` and `run_decision_pipeline(...)`.
  - Client writes harness version/hash into `trace_metadata`.
  - Worker writes eval case/result after successful run and before marking job succeeded.

- [ ] **Step 4: Verify GREEN**
  ```bash
  uv run pytest tests/e2e/test_pulse_agent_runtime_flow.py tests/unit/test_pulse_candidate_worker.py -q
  ```

## Final Verification

- [ ] Run focused suite:
  ```bash
  uv run pytest tests/unit/test_pulse_agent_runtime.py tests/integration/test_pulse_repository.py tests/unit/test_pulse_candidate_worker.py tests/e2e/test_pulse_agent_runtime_flow.py -q
  ```
- [ ] Run lint:
  ```bash
  uv run ruff check .
  ```
- [ ] Run full test suite if focused suite and lint pass:
  ```bash
  uv run pytest
  ```
- [ ] Regenerate DB schema docs if schema changed:
  ```bash
  uv run python scripts/regen_db_schema.py
  ```

## Self-Review

- Spec coverage: covers Cookbook-inspired harness versioning, trace/eval linkage, deterministic regression gate, and no compatibility code.
- Placeholder scan: no TBD/TODO placeholders.
- Type consistency: `runtime_version`, `runtime_hash`, `eval_case_id`, `eval_result_id` are used consistently across schema, repository, worker, and tests.
