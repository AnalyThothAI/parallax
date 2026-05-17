# Pulse Agent Desk Redesign — Open Questions 决策记录

**日期**: 2026-05-16
**Plan**: `docs/superpowers/plans/active/2026-05-16-pulse-agent-desk-redesign-plan-cn.md`
**Spec**: `docs/superpowers/specs/active/2026-05-16-pulse-agent-desk-redesign-cn.md`

---

## OQ-1 Investigator tool call 上限

**锁定**: `cex=3, meme=5`，配置写入 `workers.yaml` 的 `pulse_candidate.investigator_max_tool_calls.{cex,meme}`。

**理由**: 与 spec §4.4 默认值一致；cex 信号 (高质量低频) 不需太多 tool round-trip；meme 信号 (低质量高频，叙事更模糊) 给更宽预算。Phase 1 上线 7 天后看实际 `tool_calls_count` 分布再调整。

**实施位置**: Task 4 工具内 counter + Task 6 client 读 workers.yaml + `gmgn-twitter-intel init` 默认模板。

---

## OQ-2 DecisionMaker fallback tool

**锁定**: **启用** `get_target_recent_tweets`，`max_turns=3`。

**理由**: spec §4.2 设计意图。DecisionMaker 在 Investigator observation 不足时 (data_gaps 非空、bull/bear 双 absent) 能补查关键证据避免错误锚定。max_turns=3 给 1 次 tool call + 1 次结构化输出 + 1 次 fallback retry 的空间。Phase 1 上线后若 DecisionMaker tool call 命中率 <5% 则下个迭代禁用。

**实施位置**: Task 6 `_run_decision_maker` Agent `tools=[get_target_recent_tweets]`。

---

## OQ-3 GMGN description backfill

**实施时新发现 — 锁定路线变更**: GMGN OpenAPI **不返回** description 字段。

**实测验证**（2026-05-16，5519 ready profile）:
- `raw_payload_json->'link'->>'description'` 全部为空字符串
- `raw_payload_json->>'description'`（root）全部 NULL
- 现有 mapper 链路（`openapi_client.py:239` + `providers_wiring.py:244` + `asset_profile_refresh.py:121`）**已正确传递 description**，但源端无数据
- DB 5519/5519 行 description=NULL **不是 mapper bug**

**新决策**:
1. **Task 1 跳过 mapper 修改**（无 bug 可修）
2. "官方叙事"角色降级为 GMGN 实际提供的字段集合：`symbol / name / website / twitter_username / telegram / banner_url / logo_url`
3. Investigator 工具 `get_official_token_profile`（Task 4）暴露这些字段 + 显式注明 `description: null, description_source_available: false`
4. Prompt 内引导模型：若 description 为 null 则结合 `name / symbol / twitter_username / website` 推断官方定位
5. 不做 backfill（无意义）

**实施位置**: Task 1 文档化此发现，**不动 code**；Task 4 工具按上述字段集返回；Task 5 prompt 加引导。

---

## OQ-4 `_FORBIDDEN_EXECUTION_RE` 反测

**锁定**: **31 个候选字段名/值全部通过反测，0 误伤**。

**实测**（2026-05-16）:
```
checked: ['1h', '4h', '24h', 'has_playbook', 'watch_signals', 'exit_triggers',
          'monitoring_horizon', 'investigator', 'decision_maker',
          'research_only_gate', 'narrative_archetype', 'narrative_thesis_zh',
          'bull_view', 'bear_view', 'playbook', 'absent', 'weak', 'moderate',
          'strong', '关注 watched_author 接力', '流动性回撤 >20% 触发退出',
          '提及量停止增长', '关键作者抛售', 'evidence_event_urls',
          'memetic', 'utility', 'migration', 'infra', 'ip', 'thematic', 'unclear']
total: 31, flagged: 0
```

**结论**: 无字段名/值需改名。Pydantic `_reject_execution_language` 验证器对 playbook 字段 + watch_signals/exit_triggers 文本继续承担运行时校验。

**实施位置**: Task 3 Pydantic validator 强制运行时校验。

---

## OQ-5 `pulse_agent_runs.outcome` `abstain_critic_veto` enum 值处置

**锁定**: 保留作历史只读，不动 CHECK。

**理由**:
1. 老 outcome 行（DB 实测含此值）仍需可读，DROP CHECK 重建会触发 reviewer P0-1 类型 immediate-validate 风险
2. 新写路径（Task 6 client 删 critic veto 分支）已不再产生此值
3. enum 残留无运行时危害（仅是 CHECK 允许的合法值）
4. 与项目其它 hard-cut 历史枚举处理一致

**实施位置**: 不需 alembic 改动；Task 10 grep 防御允许此值出现在历史读路径中。

---

## OQ-6 prompt 文件命名

**锁定**: `prompts/{investigator,decision_maker}.md` 单文件，路由段落内联。

**理由**:
1. KISS：2 个文件 vs 4 个文件（{role}_{route}.md 形式）
2. 复用现有 anti-injection prefix 与角色定位段（route 段是末尾的"侧重指引"，~5-10 行）
3. prompt diff 更容易 review（route 段并排可对比）
4. loader 实现简单（read file → 按 markdown ##  小节切 route 段）

**实施位置**: Task 5 prompt_loader.py + 2 个 markdown 文件。

---

## 决策完成确认

全部 6 个 OQ 已锁定，可进入 Task 1 实施。
