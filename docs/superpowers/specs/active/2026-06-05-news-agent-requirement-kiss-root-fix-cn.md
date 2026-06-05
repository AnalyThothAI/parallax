# News Agent Requirement KISS Root Fix

## 背景

当前 News 页大量显示 `AGENT SKIP`，但用户看不到原因。对子 agent 审计和真实库抽样显示，问题不是单一阈值，而是同一条新闻“是否需要 agent、为什么不需要、UI 应如何展示”在多个地方重复推断：

- `NewsItemProcessWorker` 入队前跑 agent eligibility。
- `NewsItemBriefWorker` claim 后再跑一次 policy。
- `NewsPageProjection` 缺 current brief 时再临时推断 `pending/not_required`。
- `cleanup_stale_brief_input_targets` 用 SQL 手写一份近似 policy。
- 前端只显示裸 `AGENT SKIP`，不展示 reason。

这违反 Kappa/CQRS 的事实优先和单一决策权原则，也让 `AGENT WAIT/SKIP` 随投影时间、旧队列、旧字段 fallback 变化。

## 目标

建立一个最小、持久化、可审计的 agent requirement contract：

- `analysis_admission` 只决定新闻是否进入 crypto analysis 语义域。
- `agent_requirement` 只决定是否需要跑 single-item brief agent。
- `agent_requirement` 由 `NewsItemProcessWorker` 唯一写入 `news_items`。
- `NewsItemBriefWorker`、`NewsPageProjection`、前端只读取该 contract，不重新推断 policy。
- `AGENT SKIP` 必须显示具体原因。
- 旧 research tool UI/类型不再作为当前 brief 的一等展示。

## 非目标

- 不把 provider score 当作 crypto identity。
- 不用高分 provider signal 直接覆盖 admission。
- 不引入外部检索工具或恢复 retired tools。
- 不把旧 run/tool artifact 继续伪装成当前 agent evidence。

## Contract

在 `news_items` 增加：

- `agent_requirement_status`: `required | not_required`
- `agent_requirement_reason`: `eligible | analysis_not_admitted | below_score_threshold | classification_missing | item_not_processed | source_not_provider_signal | missing_provider_score | published_too_old | insufficient_crypto_evidence`
- `agent_requirement_priority`: integer
- `agent_requirement_json`: policy basis，包括 provider score、admission status、crypto evidence、thresholds、decided_at_ms
- `agent_requirement_version`

状态含义：

- `required`: 已处理、已 admitted、provider signal 符合 brief policy，应存在或等待 `brief_input` / current brief。
- `not_required`: 不应调用 agent，reason 必须解释原因。

## 数据流

```text
news_fetch
  -> news_items raw
  -> news_item_process
      -> entities / token_mentions / fact_candidates
      -> content_classification
      -> analysis_admission
      -> agent_requirement
      -> if required enqueue brief_input
      -> enqueue page
  -> news_item_brief
      -> claim brief_input
      -> read persisted agent_requirement
      -> run agent only if required
      -> write current brief
      -> enqueue page
  -> news_page_projection
      -> read current brief + agent_requirement
      -> build explicit agent_signal
  -> UI
      -> display status + reason
```

## 根修要求

1. 删除 page projection 中重新运行 `news_item_agent_brief_eligibility` 的业务判断。
2. 删除 cleanup SQL 中复制 eligibility policy 的 CASE 分支，改为读取持久化 requirement。
3. `NewsItemBriefWorker` 不再重跑完整 policy，只信任持久化 requirement；如果不 required，写 `skipped/not_required` 的 run 结果或清理队列。
4. 前端 badge 展示 reason，detail 页展示 admission、agent requirement、processing terminal error。
5. 删除当前前端对 retired research tools 的一等展示；旧 run 只能作为折叠 legacy audit。
6. `news_entity_extraction` 输出必须匹配 DB identity，避免 title/body 同文导致 process terminal failure。
7. 真实数据重放后，最近 24h 不应存在：
   - 低分或未 admitted 行显示 `AGENT WAIT`
   - `AGENT SKIP` 无 reason
   - `process_terminal_failed` 来自 `ux_news_item_entities_identity`
   - current News UI 展示 retired `get_target_news_context/search_news_archive/get_observation_history` 为当前工具

## 验证

- Unit tests:
  - entity duplicate title/body 不触发重复 repository identity。
  - agent requirement policy 覆盖 admitted high score、below threshold、analysis_not_admitted、classification_missing。
  - page projection 只读取 requirement，不重跑 policy。
  - cleanup stale brief targets 读取 requirement，不复制 policy。
  - frontend `AGENT SKIP` 展示 reason。
- Integration/runtime:
  - rebuild Docker app。
  - backfill/reprocess recent News rows。
  - reproject 24h page rows。
  - audit `news_page_rows` status/reason 分布。
  - audit logs 无 retired tool runtime、无 duplicate entity terminal failure。
