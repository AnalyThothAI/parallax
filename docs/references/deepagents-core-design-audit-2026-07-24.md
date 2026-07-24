# DeepAgents Core 与 Parallax 宏观设计审计

- 日期：2026-07-24
- 范围：`/macro` 六页证据、八类风险暴露、Daily Macro Judgment、DeepAgents runtime
- 状态：hard-cut 已实施，真实 publication 与浏览器验收仍待闭合
- 目标：区分数据链路与研判逻辑问题，并确定 capability-first 替代架构
- 变更边界：记录根因、已确认架构决策与最终验证证据

## 1. 执行结论

当前宏观不可用不是单一前端问题，而是 evidence selection、session cutoff、availability、anchor readiness 与研判逻辑收缩叠加。
前端“八类风险全部证据不足”基本忠实反映 read model；Daily 虽真实使用 `create_deep_agent` 和原生 `task`，主要流程却由 Python middleware 强制。
模型不能自主检查、补读、规划、委派和闭合矛盾，当前形态更接近“Analyst + Reviewer + 最多一次修订”的结构化流水线。
删除测试同样失败：换成两次结构化调用，产品能力几乎不变。
应保留 PostgreSQL 事实、point-in-time cutoff、稳定身份、引用完整性和原子持久化；readiness、gap、计划、上下文、委派、审阅、修订和中文综合交给 DeepAgent。
推荐 completed-session DeepAgents 宏观研究 runtime，常规 worker
只调用零参数 `run()`，读面只调用 `read()`。

## 2. 证据与版本边界

当前实现证据：

- `src/parallax/domains/macro_intel/runtime/daily_macro_judgment_worker.py`
- `src/parallax/integrations/model_execution/macro_judgment_deepagent.py`
- `src/parallax/domains/macro_intel/services/daily_macro_judgment.py`
- `src/parallax/app/runtime/worker_factories/macro_intel.py`
- `tests/architecture/test_product_ai_hard_delete.py`
- `docs/sdd/features/completed/2026-07-23-daily-macro-spy-judgment/`

Parallax 当前安装和固定的 DeepAgents 版本是 `0.6.12`；本地源码也处于该版本时代，但本地 `main` 已与官方远端分叉且 examples 有额外加固，不能当作当前官方实现。
本报告以 installed `0.6.12` 为运行基线；“latest stable”不能由 GitHub `main` 推断。
实施前必须重新核验 release notes 与 PyPI，因为发布版本可能在 cutoff 后变化。

官方入口：

- [DeepAgents repository](https://github.com/langchain-ai/deepagents)
- [DeepAgents overview](https://docs.langchain.com/oss/python/deepagents/overview)
- [PyPI deepagents](https://pypi.org/project/deepagents/)
- [Deep Research example](https://github.com/langchain-ai/deepagents/blob/main/examples/deep_research/agent.py)
- [Text-to-SQL example](https://github.com/langchain-ai/deepagents/blob/main/examples/text-to-sql-agent/agent.py)
- [Content Builder example](https://github.com/langchain-ai/deepagents/blob/main/examples/content-builder-agent/content_writer.py)
- [Ralph Mode example](https://github.com/langchain-ai/deepagents/blob/main/examples/ralph_mode/ralph_mode.py)

## 3. 数据链路与逻辑问题

### 3.1 数据链路

六页与八类风险依赖完成交易日、market cutoff、available time、历史 anchor 和投影快照；当前症状显示 exact-session observation 与 comparable-history anchor 没有同时就绪。
cutoff 日、available-at 和查询 end-exclusive 语义必须复核，但 point-in-time 约束不能放松：cutoff 后入库的事实不能假装此前已知。
正确诊断必须区分以下原因：

- 事实确实未在 cutoff 前可得；
- 事实已可得但 selection query 排除；
- 当前值存在但历史 anchor 不存在；
- read model 已过期；
- worker 或 provider 未运行；
- evidence normalization 丢失 series identity。

八张卡统一显示“关键证据不足”掩盖了不同故障；gap 应携带 source、concept、期望时间、最近可用时间与机器可读原因。

### 3.2 研判逻辑

当前 Agent 读取约 60k 字符的 pack view，每个 concept 主要暴露 deterministic page 已引用的最新 evidence。
它不能自主检查完整历史、相邻窗口或被页面规则排除的事实。
`_workflow_contract_middleware` 强制 pack read、submit、reviewer、可选 revise、再停止；Reviewer 也被强制先读 pack 与 draft。
deterministic gate 还按 pack health 阻断、强制 horizon `no_call`、校验预计算 health 和 reviewer disposition。
readiness/gap 因此属于 Python；英文 Daily 也说明中文不是可靠的端到端契约。

## 4. 当前 compliance matrix

| DeepAgents 能力 | 状态 | 结论 |
|---|---|---|
| installed runtime | 符合 | 使用真实 `0.6.12` |
| `create_deep_agent` | 符合 | 不是普通函数伪装 |
| 原生 `task` | 部分 | 有隔离 Reviewer，但调用时机被强制 |
| 工具能力 | 不符合 | Parallax 自建 allowlist 收缩了 DeepAgents 能力 |
| Agent 自主计划 | 不符合 | 没有动态 research plan |
| 渐进证据披露 | 不符合 | 主要是一次整包读取 |
| 观察后选择工具 | 不符合 | middleware 决定顺序 |
| 动态上下文管理 | 部分 | Reviewer 隔离，主上下文固定 |
| 自主委派 | 不符合 | 固定 Reviewer |
| 自主 revision loop | 不符合 | 最多一次，由代码状态机规定 |
| readiness ownership | 不符合 | compiler 和 worker gate 决定 |
| gap ownership | 不符合 | deterministic page/risk rules 决定 |
| 反证探索 | 部分 | prompt 要求，但缺定向检索 |
| 结构化输出 | 符合 | schema 与引用转换存在 |
| 中文端到端契约 | 不符合 | 实际内容仍可为英文 |
| point-in-time 引用 | 符合 | cutoff、hash、reference 有机械校验 |
| 审阅痕迹 | 部分 | 最终 review 在，首稿/revise 依据不足 |
| checkpoint/resume | 不符合 | job retry 不等于 Agent 恢复 |
| 删除测试 | 不通过 | 两次结构化调用可保留大部分能力 |

总体判断：退役实现的 Agent-first 能力不合格；工具限制本身不是质量证明。

## 5. Dormant LLM hard-delete

architecture test 已标记以下模块为 dormant：

- `src/parallax/integrations/model_execution/execution_gateway.py`
- `src/parallax/integrations/model_execution/output_schema.py`
- `src/parallax/integrations/model_execution/structured_json_strategy.py`
- `src/parallax/integrations/model_execution/usage.py`
- `src/parallax/platform/agent_capabilities.py`
- `src/parallax/platform/agent_execution.py`
- `src/parallax/platform/agent_hashing.py`

新 runtime 不应重新依赖这些通用抽象；确认零生产调用后直接删除，不增加 wrapper、alias 或 fallback gateway。
唯一模型 seam 由宏观研究 module 拥有：生产 adapter 连接真实 provider，测试 adapter 提供 scripted/mock model。

## 6. Capability-first 新方向

目标是在冻结事实范围内最大化研究能力，不用 Parallax 自建安全或
“专业性” gate 收缩 DeepAgents。
DeepAgent 应能够：

- 检查 evidence catalog；
- 按问题、concept、series、window 和来源自由查询；
- 读取指定 citation 的完整事实；
- 比较当前值、历史 anchor 与变化速度；
- 建立可审计 hypothesis ledger；
- 主动寻找反证并解释 gap；
- 判断证据是否足够；
- 自主选择 specialist、review 与 revision；
- 产出统一中文报告；
- 提交一个完成交易日 publication。

Parallax 不注册工具排除表。DeepAgents 原生文件系统以及 backend 实际
提供的 `execute` 可用于计算、比较和草拟；所有可发表市场事实仍必须来自
当前冻结 scope 的只读工具并闭合到 `source_ref`。实时 Web、provider
直连或数据库读取不是另一条事实入口。

## 7. DeepAgents-first target ownership

| 所有者 | 必须拥有 |
|---|---|
| PostgreSQL | material facts、稳定身份、snapshot、checkpoint、audit、publication |
| Parallax code | 日历、cutoff、可见性、事务、引用完整性 |
| DeepAgent | readiness、gap、计划、上下文、研究路径、委派、review、revision、中文综合 |
| LLM adapter | provider protocol、认证、超时、错误分类、响应映射 |
| UI/read model | 呈现 publication 与结构化 gap，不重新研判 |

“无 semantic deterministic gates”仍保留事实和存储完整性：代码拒绝未来事实、未知引用与身份冲突。
代码不应通过阈值替 Agent 决定 evidence sufficient、方向或 `no_call`。

## 8. 三种 interface 方案

### 8.1 A：最小 `advance`

```python
class MacroResearchRuntime(Protocol):
    async def advance(self) -> MacroResearchOutcome: ...
```

runtime 自己选择最早未完成的 eligible session，并隐藏 freeze、plan、tools、delegation、review、revision、checkpoint 与 publish。
它的 interface、误用风险最小，depth 与 caller leverage 最高；代价是 backfill 和交互研究暂不属于该 interface。

### 8.2 B：program runtime

```python
class MacroResearchRuntime(Protocol):
    async def run(self, program: MacroResearchProgram) -> MacroResearchOutcome: ...
```

program 可描述 target、policy、budget、specialists 与 publication mode，适合未来多资产、多 horizon 和 shadow/canary。
它最灵活却容易泄露 orchestration；只有出现多个真实 program caller 后才应引入。

### 8.3 C：completed-session product module

```python
class CompletedSessionMacro(Protocol):
    async def run(self, session_date: date | None = None) -> MacroSessionView: ...
    async def read(self, session_date: date | None = None) -> MacroSessionView | None: ...
```

`run()` 默认研究最近完成交易日并允许显式 backfill；`read()` 是
persisted-only 的当前或历史读取。二者都不暴露 program、tool order、
locale、risk taxonomy、readiness policy 或 checkpoint 操作。module 内部仍
验证显式日期确为已完成 session，因此调用方不能绕开 eligibility。

| 维度 | A advance | B program | C completed-session |
|---|---|---|---|
| interface | 最小 | 最大 | 中等 |
| leverage | 最高 | 中等 | 高 |
| locality | 最高 | 容易外泄 | 高 |
| backfill | 独立 admin module | 原生 | 原生 |
| 误用风险 | 最低 | 最高 | 中等 |
| 推荐 | 次选 | 暂不采用 | 首选 |

最终推荐 C。当前已经存在自动 completed-session 运行与显式历史读取两个
真实 caller；C 比 A 多一个窄读方法，却把 backfill、幂等恢复和 persisted
read 的产品语义保留在同一深模块内。B 仍是没有真实多 program caller 的
预付复杂度。

## 9. Target hidden implementation

seam 建议位于 `domains/macro_intel/services/completed_session_macro.py`；
外部只有 `run/read`，内部隐藏：

1. 选择并 lease session；
2. 创建 point-in-time snapshot；
3. 恢复 session checkpoint；
4. 构造 DeepAgent 与只读 evidence tools；
5. 提供 specialist 与 reviewer；
6. 让 Agent 自主研究和修订；
7. 做机械完整性验证；
8. 原子保存 outcome、audit、publication；
9. 返回产品类型。

允许 schema、session/cutoff/hash、citation、可见性、identity 与副作用检查；不允许缺失计数判 `no_call`、固定 risk state、关键词中文 gate、固定 review 次数或 renderer 替代综合。

## 10. 已确认 hard-cut 范围

owner 已确认以下内容一起退役：

1. 六页 deterministic 宏观研判；
2. 八类风险状态与证据充足度规则；
3. Daily readiness、health、`no_call` 与 reviewer semantic gates；
4. forced tool-order 和 one-revision middleware；
5. dormant LLM gateway、schema strategy、usage 与 platform middleware。

这不是保留旧判定再外加 Agent narrative：DeepAgents 将拥有规划、取证、分工、反证、复核、中文叙事与最终语义判断。
六页和八类 lane 不能继续作为隐藏 gate 或第二套 business truth；相似 UI 导航也只能消费新 publication。
旧 snapshot 仅可用于有截止日期的 A/B/C shadow eval；切换后必须删除双写和兼容路径。

## 11. A/B/C eval

候选：

- A：当前 forced-workflow DeepAgents；
- B：KISS `create_agent` 或两次结构化调用；
- C：目标 DeepAgents-owned runtime。

评估样本应覆盖完整 session、来源延迟、跨资产矛盾、稀疏文本、未知
引用与英文倾向。以下是一次性实现验收的观察维度，不进入运行时评分、
发布阈值或人工审批：

- 中文叙事是否自然、完整；
- 引用是否准确闭合；
- 是否主动寻找关键反证；
- gap 是否具体、诚实且不阻断 Agent 给出判断；
- hallucination 与 causal jump；
- reviewer 是否实质挑战论证；
- p50/p95 latency、token、provider cost。

实现验证只要求机械事实闭合、checkpoint 恢复、原子 publication 和产品
可读性得到真实回执；内容是否专业由 DeepAgent 产物的盲审判断，不由
计数、覆盖率、语言比例或固定风险分类决定。

## 12. 实施与最终建议

1. 先修复并验证 cutoff、availability 与 anchor 链路。
2. 固化 point-in-time snapshot 机械 contract。
3. 建立 A/B/C frozen-session eval corpus。
4. 实现方案 C 的 `CompletedSessionMacro.run/read` seam。
5. 增加渐进 tools、checkpoint、specialists 与 review。
6. shadow 运行 C，完成真实 provider E2E 与盲审。
7. 按已确认范围一次性切换唯一 writer 与 read model。
8. 删除六页研判、八类规则、Daily semantic gates 与 forced middleware。
9. 删除 dormant LLM stack、双写与兼容路径。

不要再用 prompt patch 或更多 deterministic gate 修补当前链路。
若仍是固定 draft-review-revise，就删除 DeepAgents 并用简单 structured
call；若是深度研究，采用 C 的 completed-session 深模块。
DeepAgents 必须用动态工具、上下文、委派、恢复与语义质量证明 leverage；最终只能有一个 writer、一个 stable identity 和一个事实来源。
