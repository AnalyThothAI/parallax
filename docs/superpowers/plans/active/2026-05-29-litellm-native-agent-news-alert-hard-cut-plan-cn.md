# Plan - LiteLLM Native Agent and News High-Score Alert Hard Cut

**Status:** Implemented - verification complete
**Date:** 2026-05-29
**Owning spec:** `docs/superpowers/specs/active/2026-05-29-litellm-native-agent-news-alert-hard-cut-cn.md`
**Worktree:** `.worktrees/litellm-native-agent-news-alert-hard-cut/`
**Branch:** `codex/litellm-native-agent-news-alert-hard-cut`

**Goal:** 按已批准 spec 做一次 hard cut：删除 OpenAI/OpenAI Agents SDK runtime 路径，建立 LiteLLM-native 共享执行面；同时把 News 高分 item 变成“agent brief ready 后去重推送”的干净链路，并把 Narrative 和 Signal Pulse 的边界重新梳理清楚。

**Architecture:** 底座重构，domain 队列不合并。`news_item_brief`、`pulse_candidate`、`mention_semantics`、`token_discussion_digest`、`enrichment`、`handle_summary` 都迁到同一个 LiteLLM-native execution plane；News alert 是 Notifications rule，不新增散装推送 worker；Narrative 作为可关 bulk tier；Signal Pulse 保留 evidence-first 决策面，不作为 News 高分推送 truth source。

**Tech Stack:** Python 3.13, Pydantic v2, LiteLLM Python SDK, psycopg/PostgreSQL, FastAPI, pytest, ruff, existing Notifications delivery adapters.

---

## Chain Diagnosis

- [x] **底层 LLM 链路必须重构。** 当前 `LLMGateway` 直接构造 `AsyncOpenAI`，`AgentExecutionGateway` 和 audit vocabulary 仍绑定 `openai_agents_sdk`。这不是配置问题，是 runtime primitive 错位。
- [x] **News 链路有明确 bug/设计冲突。** 当前 `NewsItemBriefWorker` 遇到 provider signal 会 skip，导致 OpenNews 高分 item 正好不会生成 agent brief；这会直接阻断“score >85 agent 总结后推送”。
- [x] **Notifications 链路可复用，但 dedup 要梳理。** 现有 durable notification fact 和 delivery worker 是对的；问题是 semantic duplicate / external cooldown 目前是 Pulse-specific，需要抽成通用 notification signature policy。
- [x] **Narrative 不建议重写成新系统。** 它应降级为可关的 `bulk_analysis` tier：关闭 `narrative_admission`、`mention_semantics`、`token_discussion_digest` 后，不能继续产生新 narrative backlog，也不能阻塞 News/Pulse。
- [x] **Signal Pulse 架构保留，健康治理单独做。** Pulse evidence-first / gate / write model 边界是对的；本计划只迁移它的 LLM 底座和确认它不被 News alert 耦合。dead/stale job 清理是后续运维/修复计划，不塞进本 hard cut。

## Hard-Cut Rules

- [x] 不保留 `openai` / `openai-agents` direct dependency、source import、execution path；`openai` 只允许作为 LiteLLM 的传递依赖出现在 `uv.lock`。
- [x] 不保留 `LLMGateway.openai_client()` 兼容方法。
- [x] 不保留 `integrations/openai_agents` live package 或 `OpenAIAgents*Client` 命名。
- [x] 不加 `use_litellm`, `legacy_openai`, `dual_backend` 之类长期配置开关。
- [x] 不创建 central durable `agent_tasks` 表。
- [x] 不从 News worker 直接推送 PushDeer/Apprise/Telegram。
- [x] 不让 provider summary 作为 external push 的 agent summary fallback。
- [x] 不让 News 写 Pulse read models，也不让 Pulse 写 News notification facts。

## Pre-flight

- [ ] Spec is approved:
  ```bash
  sed -n '1,120p' docs/superpowers/specs/active/2026-05-29-litellm-native-agent-news-alert-hard-cut-cn.md
  ```

- [ ] Create isolated worktree:
  ```bash
  git worktree add .worktrees/litellm-native-agent-news-alert-hard-cut -b codex/litellm-native-agent-news-alert-hard-cut main
  cd .worktrees/litellm-native-agent-news-alert-hard-cut
  git branch --show-current
  git status --short
  ```

- [ ] Confirm live config paths before real-data diagnostics:
  ```bash
  uv run parallax config
  ```
  Expected: `config_path` and `workers_config_path` point at `~/.parallax/`; no secret values printed.

- [ ] Capture current chain health without mutation:
  ```bash
  uv run parallax ops worker-status
  uv run parallax ops news-dedup-diagnostics
  uv run parallax pulse health
  ```

- [ ] Run baseline checks:
  ```bash
  uv run ruff check .
  uv run pytest tests/architecture/test_agent_execution_plane_contracts.py tests/architecture/test_news_intel_boundaries.py tests/architecture/test_pulse_no_compat.py -q
  uv run pytest tests/unit/domains/news_intel tests/unit/test_notification_rules.py tests/unit/test_provider_wiring_agent_execution_gateway.py -q
  ```

Known-failing baseline tests: record exact failures before implementation. If PostgreSQL integration suites cannot run locally, record the environment gap and run them before merge in the standard DB-backed environment.

## File-Level Edits

### Dependencies

- `pyproject.toml:10-23`
  - Add `litellm`.
  - Remove `openai` and `openai-agents`.
  - Keep `apprise`.
- `uv.lock`
  - Regenerate after dependency change.
- `pyproject.toml:150`
  - Remove stale OpenAI/OpenAI Agents ignore entries if no longer needed; add LiteLLM typing ignore only if required.

### Model execution plane

- Delete live package:
  - `src/parallax/integrations/openai_agents/`
- Create provider-neutral package:
  - `src/parallax/integrations/model_execution/__init__.py`
  - `src/parallax/integrations/model_execution/execution_gateway.py`
  - `src/parallax/integrations/model_execution/structured_json_strategy.py`
  - `src/parallax/integrations/model_execution/output_schema.py`
  - `src/parallax/integrations/model_execution/usage.py`
- `src/parallax/app/runtime/llm_gateway.py:1-85`
  - Replace OpenAI client factory with a small LiteLLM execution config/value object or fold it into `model_execution`.
  - Remove `AsyncOpenAI`, `httpx.AsyncClient` client cache, and `agents.set_tracing_export_api_key`.
- `src/parallax/platform/agent_execution.py:18-260`
  - Rename runtime version to LiteLLM-native.
  - Change audit defaults: `provider="litellm"`, `backend="litellm_sdk"`.
  - Keep lane policy, reservation, error classes, request/result audit models.
- `src/parallax/platform/agent_capabilities.py`
  - Replace OpenAI/DeepSeek capability names with LiteLLM provider alias semantics.
  - Preserve request options needed for JSON object mode and model-specific provider kwargs.

### Runtime wiring

- `src/parallax/app/runtime/provider_wiring/openai.py:1-240`
  - Delete or replace with `provider_wiring/model_execution.py`.
  - Rename all `OpenAI*Provider` wrappers to neutral names.
- `src/parallax/app/runtime/providers_wiring.py`
  - Wire the new model execution providers into runtime provider bundle.
- `src/parallax/app/runtime/bootstrap.py`
  - Construct one shared LiteLLM-native execution gateway when LLM config is present.
  - Close only resources the new gateway actually owns.
- `src/parallax/platform/config/settings.py:793-884`
  - Keep lane keys, but make model/provider config LiteLLM-native.
  - Add explicit tier/group disablement for `bulk_analysis` or narrative analysis.
  - Keep unknown lane validation strict.

### Domain provider migrations

- Narrative:
  - Replace `OpenAIAgentsNarrativeIntelClient` with LiteLLM-backed provider under neutral integration naming.
  - Ensure `narrative_admission`, `mention_semantics`, and `token_discussion_digest` can be disabled as a group without enqueueing new backlog.
  - Keep existing `narrative_model_runs` domain ledger.
- News:
  - Replace `OpenAIAgentsNewsItemBriefClient` with LiteLLM-backed brief provider.
  - Keep `NewsItemBriefInputPacket`, `NewsItemBriefPayload`, and validator.
  - Keep `news_item_agent_runs` and `news_item_agent_briefs`.
- Pulse:
  - Replace `OpenAIAgentsPulseDecisionClient` with LiteLLM-backed provider.
  - Keep evidence packet, stage plan, claim verifier, recommendation clipper, write gate.
  - Do not change Pulse thresholds or write model semantics in this hard cut.
- Social / Watchlist:
  - Replace OpenAI-named providers with LiteLLM-backed providers.
  - Keep domain schemas and run ledgers.

### News high-signal brief priority

- `src/parallax/domains/news_intel/runtime/news_item_brief_worker.py:49-173`
  - Remove provider-signal skip behavior at lines around `131-135`.
  - Treat provider signal as part of packet/context and prioritization.
- `src/parallax/domains/news_intel/repositories/news_repository.py:1504-1571`
  - Add/read high-signal candidate ordering from `news_page_rows` or source rows without request-time LLM.
  - Prioritize `score >= threshold` and missing/stale current brief.
- `src/parallax/domains/news_intel/services/news_page_projection.py:212-252`
  - Preserve provider score and provider signal, but expose agent brief/alert eligibility as distinct fields.
  - Do not let provider signal hide ready agent brief state.

### News notification rule

- `src/parallax/domains/notifications/services/notification_rules.py:36-65`
  - Inject News read model/repository into `NotificationRuleEngine`.
  - Add `news_high_signal` evaluation after existing rules.
- `src/parallax/domains/notifications/services/notification_rules.py:314-412`
  - Keep Pulse-specific rule behavior but move stable signature helpers into shared notification signature helpers.
- `src/parallax/domains/notifications/repositories/notification_repository.py:22-198`
  - Generalize semantic duplicate and external cooldown logic beyond Pulse.
  - Preserve existing Pulse notification behavior.
- `src/parallax/domains/notifications/runtime/notification_worker.py:82-155`
  - Ensure News high-signal candidates enqueue external deliveries only when channels/severity allow.
- `src/parallax/platform/config/settings.py`
  - Add `notifications.rules.news_high_signal` defaults.
  - External threshold defaults to `90`; `85` path requires token-impact/content/source filters.

### Architecture tests and docs

- `tests/architecture/test_agent_execution_plane_contracts.py:81-185`
  - Replace OpenAI-specific allowlists with LiteLLM-only constraints.
  - Assert no live source imports OpenAI/OpenAI Agents SDK.
- `tests/architecture/test_news_intel_boundaries.py:11-25`
  - Keep News/Pulse boundaries strict.
- `tests/architecture/test_pulse_no_compat.py:23-30`
  - Extend guardrails to reject OpenAI integration naming if needed.
- Update:
  - `docs/ARCHITECTURE.md`
  - `docs/WORKERS.md`
  - `docs/WORKER_FLOW.md`
  - `docs/CONTRACTS.md`
  - `docs/RELIABILITY.md`
  - `src/parallax/domains/news_intel/ARCHITECTURE.md`
  - `src/parallax/domains/pulse_lab/ARCHITECTURE.md`

## Storage / Migrations

- [ ] No new central agent queue table.
- [ ] No new News alert table in the first cut; use existing `notifications`, `notification_deliveries`, and payload/dedup fields.
- [ ] Add indexes only if query plans show the News high-signal rule scans too much data. Candidate indexes, if needed, belong on existing `news_page_rows` JSON score/status fields or a projected scalar already present.

## PR Breakdown

1. **PR 1 - Guardrails and dependency hard cut**
   - Update dependency declarations and architecture tests.
   - Add failing checks for forbidden `openai`, `agents`, `integrations.openai_agents`, `OpenAIAgents*`, and `openai_agents_sdk` audit strings.
   - No production behavior change beyond test scaffolding.

2. **PR 2 - LiteLLM-native execution plane**
   - Create `integrations/model_execution`.
   - Port lane reservation, timeout, circuit breaker, audit, JSON object validation, usage extraction to LiteLLM `acompletion`.
   - Remove `LLMGateway.openai_client()`.

3. **PR 3 - Domain provider migration**
   - Migrate News, Pulse, Narrative, Social, Watchlist provider clients to the new execution plane.
   - Keep each domain's queues, ledgers, validators, and finalizers intact.
   - Remove `integrations/openai_agents`.

4. **PR 4 - Narrative tier isolation**
   - Add group/tier disablement for narrative bulk analysis.
   - Ensure disabling narrative trio stops new admission/semantics/digest work.
   - Verify News and Pulse do not require current narrative digest.

5. **PR 5 - News high-signal brief priority**
   - Remove provider-signal skip from `NewsItemBriefWorker`.
   - Prioritize high provider score / missing ready brief items.
   - Keep provider signal as input metadata.

6. **PR 6 - News high-signal notifications**
   - Add `news_high_signal` rule.
   - Generalize notification semantic signature and external cooldown.
   - External delivery requires ready agent brief.

7. **PR 7 - Pulse boundary and health verification**
   - Confirm Pulse runs only through LiteLLM execution plane.
   - Preserve evidence-first gate and notification semantics.
   - Document existing dead/stale cleanup as follow-up if still present after provider cutover.

8. **PR 8 - Docs and full verification**
   - Refresh canonical docs.
   - Run full targeted and global verification.
   - Record remaining operational risks in verification artefact and `docs/TECH_DEBT.md` if non-trivial.

## Acceptance Test Commands

- AC1 forbidden OpenAI runtime:
  ```bash
  rg -n "from openai|import openai|from agents|import agents|integrations\\.openai_agents|OpenAIAgents|openai_agents_sdk|AsyncOpenAI|Runner\\.run|RunConfig\\(|Agent\\(" src tests
  ```
  Expected: no live runtime/test expectations except migration notes explicitly allowed by docs.

- AC2 LiteLLM execution plane tests:
  ```bash
  uv run pytest tests/unit/integrations/model_execution -q
  ```

- AC3 worker/runtime wiring:
  ```bash
  uv run pytest tests/unit/test_provider_wiring_agent_execution_gateway.py tests/unit/test_bootstrap_worker_runtime_wiring.py tests/unit/test_worker_settings.py -q
  ```

- AC4 News brief priority and validation:
  ```bash
  uv run pytest tests/unit/domains/news_intel/test_news_item_brief_worker.py tests/unit/domains/news_intel/test_news_item_brief_validation.py tests/integration/domains/news_intel/test_news_item_agent_brief_repository.py -q
  ```

- AC5 News notifications:
  ```bash
  uv run pytest tests/unit/test_notification_rules.py tests/integration/test_notification_repository.py tests/integration/test_notification_worker.py tests/integration/test_notification_delivery.py -q
  ```

- AC6 Pulse boundary:
  ```bash
  uv run pytest tests/unit/test_pulse_candidate_worker.py tests/unit/test_pulse_candidate_gate.py tests/integration/test_pulse_desk_e2e.py tests/architecture/test_pulse_no_compat.py -q
  ```

- AC7 global checks:
  ```bash
  uv run ruff check .
  uv run pytest tests/architecture -q
  make check-all
  ```

## Rollout Order

1. Merge/deploy LiteLLM-native execution plane with external notifications still disabled.
2. Configure operator `~/.parallax/config.yaml` and `workers.yaml` for LiteLLM model aliases and lane policies.
3. Disable narrative bulk tier initially.
4. Enable News item brief worker and confirm high-score items produce ready briefs.
5. Enable `news_high_signal` in-app only.
6. Inspect 24h volume, suppression reasons, duplicate aggregation, and false positives.
7. Enable external delivery for `score >= 90` or `score >= 85` with token-impact/content/source filters.
8. Reassess Pulse health; clean dead/stale jobs in a separate follow-up if still degraded.

## Rollback

- Code rollback is branch/deploy rollback; there is no runtime dual backend.
- If LiteLLM provider calls fail, disable agent worker tiers in `workers.yaml` and keep deterministic ingest/projections running.
- If News notifications are noisy, disable only `notifications.rules.news_high_signal` or external channels; durable News facts and briefs remain intact.
- If Narrative backlog grows, keep narrative tier disabled and run a separate narrative cleanup/rebuild plan.
- If Pulse is degraded, disable Pulse notifications without disabling News high-signal notifications.

## Verification Artefact

- Create `docs/superpowers/plans/active/2026-05-29-litellm-native-agent-news-alert-hard-cut-verification-cn.md` before declaring implementation complete.
- Include full `make check-all` output, targeted command outputs, live config path confirmation, News high-score sample audit, notification dedup sample, and Pulse health snapshot.
