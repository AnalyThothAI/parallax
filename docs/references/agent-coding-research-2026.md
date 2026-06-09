# Agent Coding 规范、方案、研究方向与 `/goal` 实践手册

**调研日期：** 2026-06-09  
**适用对象：** 使用 Codex、Claude Code、GitHub Copilot coding agent、Cursor、Gemini/Android Studio Gemini、OpenHands 等 coding agent 的工程团队。  
**文档定位：** 可执行的工程手册。它不是某一个工具的宣传页，而是把 2026 年上半年已经收敛的跨工具实践、仍在变化的研究方向、以及 Codex `/goal` 命令的实际用法整理成一套可落地工作流。

## 1. 一页结论

2026 年的 agent coding 已经从“给模型一个 prompt 写代码”演化成“agent harness 工程”：模型只是核心循环的一部分，真正决定可靠性的，是任务目标、上下文边界、工具权限、执行环境、验证闭环、持久规则、技能封装、审计日志和人类反馈。

最稳定的实践可以压缩为 8 条：

1. **任务输入写成工程合同。** 每次任务至少给出 goal、context、constraints、done when。Codex 官方最佳实践也把这四项作为默认提示结构。
2. **`AGENTS.md` 放长期规则，prompt 放一次性约束。** AGENTS.md 是面向 agent 的 README，用来放构建、测试、架构、禁区和完成标准；它应短、准、可验证。
3. **计划先行，目标驱动。** 不确定的任务先 `/plan`，明确的长任务再 `/goal`。Goal 的正文既是初始提示，也是完成判定。
4. **验证是交付条件，不是附加动作。** 测试、lint、typecheck、UI 截图、日志、基准结果等必须写进 done criteria。
5. **上下文要分层加载。** 始终加载的规则要短；任务技能、参考材料、脚本、MCP 工具按需加载。Agent Skills 的 progressive disclosure 已经成为主流模式。
6. **读多写少的并行化收益最大。** 子 agent 适合调研、审查、日志分析、测试矩阵；并行写代码要用 worktree 或明确文件边界。
7. **MCP 是工具接入标准，不是安全边界。** MCP 带来通用工具协议，也带来 prompt injection、confused deputy、session hijack、本地 server compromise 等风险，需要最小权限、审批、审计和沙箱。
8. **不要只看 SWE-bench Verified。** OpenAI 已在 2026-02 指出 SWE-bench Verified 对 frontier coding capability 的信号变弱，原因包括测试缺陷和污染；评估 agent 要组合使用 issue resolution、terminal、frontend、testing、CI maintainability、context retrieval、技能使用质量等维度。

## 2. Agent Coding 的分层模型

把 coding agent 当成一个工程系统，而不是一个聊天框：

| 层 | 作用 | 常见载体 | 关键规范 |
| --- | --- | --- | --- |
| 意图层 | 本次任务要完成什么 | prompt、`/goal`、issue、PR comment | 目标清晰、范围明确、有验收标准 |
| 计划层 | 如何做、哪些文件、风险是什么 | `/plan`、spec、plan.md、任务清单 | 先调研再改动；计划可审查 |
| 持久规则层 | 团队长期工作方式 | `AGENTS.md`、`CLAUDE.md`、Copilot instructions、Cursor rules | 短、具体、可执行；靠近代码树 |
| 技能层 | 可复用任务流程 | `SKILL.md`、plugins、custom agents | 单一职责、按需加载、带脚本/模板 |
| 工具层 | 外部数据与动作 | shell、git、browser、MCP、Figma、GitHub、Linear | 最小权限、结构化接口、审计 |
| 执行层 | 文件编辑、命令运行、环境隔离 | sandbox、worktree、cloud VM、Docker | 可回滚、可复现、权限可控 |
| 验证层 | 判断是否真的完成 | tests、lint、typecheck、CI、screenshots、benchmarks | 失败要继续修；无法验证要明说 |
| 审查层 | 风险发现与质量闸门 | `/review`、code review agent、security scanner | 重点找 bug、回归、安全和测试缺口 |
| 记忆层 | 从错误中复利 | AGENTS 更新、skills、docs、memory、hooks | 只固化重复出现的非显然规则 |

这个模型解释了为什么“换一个更强模型”通常不是唯一解。Cursor 把 agent harness 拆成 instructions、tools、model；OpenHands SDK 强调 sandboxed execution、lifecycle control、multi-LLM routing；Codex 和 Claude Code 都把 skills、MCP、hooks、subagents、permissions 放进核心操作面。

## 3. 规范：如何写可执行的 Agent 任务

### 3.1 Prompt 合同模板

每个任务都可以用下面格式开头：

```text
Goal:
- 这次要改变或产出的具体结果。

Context:
- 相关文件、目录、错误日志、设计稿、issue、已知约束。

Constraints:
- 必须遵守的架构、安全、性能、产品、风格、时间或范围限制。

Done when:
- 哪些检查通过。
- 哪个行为可复现。
- 哪个文档/PR/截图/benchmark 已产出。
```

好 prompt 的判断标准不是“写得长”，而是 agent 能否回答：

- 我应该先读哪里？
- 哪些事不能做？
- 完成后如何自证？
- 如果出现冲突，哪个规则优先？

### 3.2 `AGENTS.md` 规范

`AGENTS.md` 是跨工具收敛最快的规范之一。官方 `agents.md` 把它定义为“给 coding agents 的 README”，用于提供 build steps、tests、conventions 等人类 README 不适合承载的细节。

推荐结构：

```md
# AGENTS.md

## Project Overview
- 一句话说明系统边界和核心事实源。

## Setup Commands
- Install: `...`
- Run: `...`
- Test: `...`

## Architecture Rules
- 必须遵守的模块边界、数据流、ownership。

## Code Style
- 只写非显然规则；格式化器/linter 已能保证的不要重复。

## Testing And Verification
- 修改哪些区域要跑哪些命令。
- UI、数据库、worker、安全相关变更的额外门槛。

## Security And Secrets
- 哪些文件不能读/打印。
- 哪些操作必须人工确认。

## Review Guidelines
- code review 时优先看的风险类型。
```

本仓库已有 AGENTS router，并明确要求：`AGENTS.md` 与 `CLAUDE.md` 镜像时，修改一个要同步另一个；真正细节放 `docs/`。这是一种很好的模式：root router 只放入口和高优先级不变量，长规则分流到专业文档。

写 `AGENTS.md` 的实操规则：

- **短规则优先。** VS Code/Copilot 文档也建议指令短、自包含、每条只表达一个规则。
- **写为什么。** 例如“用 date-fns，不用 moment，因为 bundle size 和维护状态”，比“不要用 moment”更稳。
- **给 canonical examples。** 指向现有文件，而不是复制整段风格指南。
- **只固化重复错误。** Cursor 的建议是看到 agent 反复犯错再加规则，不要过早优化。
- **嵌套覆盖。** 大 monorepo 在子目录放更具体的 `AGENTS.md` 或工具自己的 scoped rules。
- **规则必须可验证。** “写高质量代码”没用；“修改 web/src 后跑 npm run lint，且架构 harness 必须通过”有用。
- **定期修剪。** 如果规则已经被 linter、formatter、test 或 hook 机械保证，就从 AGENTS 中移走。

### 3.3 Agent Skills / `SKILL.md` 规范

Agent Skills 是把可复用工作流打包成目录：

```text
skill-name/
  SKILL.md
  scripts/
  references/
  assets/
```

`SKILL.md` 必须包含 YAML frontmatter，至少有：

```md
---
name: code-review
description: Review diffs for bugs, regressions, security issues, and missing tests. Use when the user asks for review.
---

Follow these steps...
```

最佳实践：

- 一个 skill 只做一件事。
- `description` 要写清触发条件和不适用边界，因为 agent 先只看到 name/description/path。
- 主 `SKILL.md` 保持短，细节放 `references/`，脚本放 `scripts/`。
- 能确定性执行的东西用脚本，判断和权衡留给说明。
- 给输入、输出、失败处理、示例。
- 对高风险 skill 加兼容性、工具依赖、权限说明。
- 定期做 skill eval，因为 OpenSkillEval 这类研究显示：有 skill 不等于 agent 会有效使用 skill，收益强依赖模型和 agent framework。

### 3.4 MCP 规范

MCP 解决的是“agent 如何用统一协议接入工具和上下文”。它适合：

- 私有文档、代码托管、issue 系统、监控、数据库、浏览器、Figma。
- 需要结构化工具调用，而不是把网页/日志复制进 prompt。
- 多个 agent/client 共享同一类工具接入。

MCP 不适合当成安全边界。必须配置：

- server allowlist，不让所有工具默认可用。
- per-tool approval mode 或等价审批。
- scoped tokens，避免把长期高权限凭证交给 agent。
- 超时、速率限制、审计日志。
- 对工具输出做“不可信输入”处理，特别是网页、issue、PR comment、外部 docs、错误消息。
- 本地 MCP server 要当成本地可执行程序审查，避免恶意 startup command、DNS rebinding、未授权 localhost 访问。

MCP 官方安全材料重点提到 confused deputy、session hijacking、local MCP server compromise 等问题；OWASP LLM Top 10 也把 prompt injection、insecure plugin design、excessive agency、supply chain vulnerabilities 列为核心风险。

### 3.5 Hooks 规范

Hooks 适合做确定性闸门，不适合放长篇软性建议。

适合 hook 的事情：

- 命令执行前拦截危险命令。
- 文件编辑后跑 formatter 或轻量静态检查。
- turn stop 时检查是否有未跑验证。
- prompt submit 时扫描 secrets。
- compact 前保存 modified files、test commands、decisions。

不适合 hook 的事情：

- 模糊架构建议。
- 需要人类判断的产品取舍。
- 长耗时、易误报的全量 CI。

原则：hook 越底层，越要稳定、快速、低误报；否则会训练用户绕过它。

## 4. 方案选型

| 方案 | 适用场景 | 推荐产物 | 风险 | 操作建议 |
| --- | --- | --- | --- | --- |
| 单 agent 交互 | 小 bug、小文档、小重构 | diff + 验证输出 | 容易跳过验证 | Prompt 写 done when，完成前要求跑检查 |
| Plan first | 模糊需求、跨模块改动 | plan/spec/task list | 计划过度或脱离代码 | 要求先读相关文件，再列文件级计划 |
| Codex `/goal` | 长任务、有明确完成标准 | 持久 goal + artifact + verification | 目标过宽会跑偏 | 目标写成可判定合同，必要时先 `/plan` |
| 子 agent 调研 | 多文件探索、日志分析、review | 摘要 + 文件引用 | 总结遗漏细节 | 限定问题、限定输出格式、主 agent 复核关键证据 |
| 并行 worktree | 多方案探索、大批量独立改动 | 多个分支/PR | merge 冲突、重复工作 | 每个 worktree 明确文件边界和验收 |
| Cloud/PR agent | issue、PR 修复、后台任务 | PR、CI、review comment | 环境差异、权限过大 | 配好 setup、secrets、sandbox、CI gate |
| Custom agent/profile | 专家角色或流程隔离 | `.github/agents/*.md` 等 | agent 过专导致上下文缺失 | description 写清职责，工具最小化 |
| Skill/plugin | 可复用流程、带资产/脚本 | `SKILL.md` + scripts/references | skill stale 或触发错误 | 版本化、eval、短描述、示例测试 |
| MCP tool layer | 私有系统、实时数据、浏览器/Figma | server config + tool policy | prompt injection、token 泄漏 | allowlist、审批、审计、短期凭证 |
| Agent SDK/平台 | 自建生产 agent | SDK 服务、队列、sandbox、telemetry | 平台复杂度高 | 先从单流程自动化，逐步加路由/权限/日志 |

## 5. `/goal` 命令详解

### 5.1 `/goal` 是什么

Codex Goal mode 是一个绑定到当前 thread 的持久目标。目标文本同时充当：

- 起始 prompt；
- 后续行动的北极星；
- Codex 判断“是否完成”的 completion criteria。

适合多步骤、长时间、可能需要自动继续推进的任务。Codex app、IDE extension、CLI 都支持 Goal mode；如果看不到 `/goal`，需要启用 `features.goals`。

### 5.2 启用方式

`~/.codex/config.toml` 或项目可信 `.codex/config.toml`：

```toml
[features]
goals = true
```

也可以在 CLI 运行：

```bash
codex features enable goals
```

### 5.3 CLI 用法

```text
/goal Finish the migration and keep tests green
```

查看当前目标：

```text
/goal
```

暂停、恢复、清除：

```text
/goal pause
/goal resume
/goal clear
```

限制：

- goal 正文必须非空。
- goal 正文最多 4000 字符。
- 更长的说明应放到文件中，然后在 goal 里引用文件路径。
- app 中目标激活后，composer 上方会显示进度，可用按钮 pause、resume、edit、clear。

### 5.4 什么时候用 `/goal`

适合：

- “把某个迁移做完并保持测试通过”。
- “深入调研并产出一篇带来源的文档”。
- “修复这个 bug，直到复现脚本通过”。
- “把 UI 改到截图验收通过”。
- “把某类 lint/test failure 清零”。
- “增加测试覆盖，覆盖这些边界条件”。

不适合：

- 目标尚不清楚，需要连续产品取舍。先 `/plan` 或让 agent 访谈你。
- 高风险操作需要频繁人工确认，例如生产数据迁移、密钥轮换、破坏性 git 操作。
- 范围像“重写整个系统”但没有分阶段验收。
- 需要 agent 长时间等待外部状态，却没有轮询/退出条件。

### 5.5 好 goal 的格式

```text
/goal 在 docs/references/agent-coding-research-2026.md 产出一篇中文调研文档，覆盖 agent coding 规范、主流方案、研究方向、Codex /goal 用法和最佳实践。

Done when:
- 至少核对 OpenAI Codex、Anthropic Claude Code、GitHub Copilot、Cursor、AGENTS.md、Agent Skills、MCP、SWE-bench/TerminalWorld/OpenHands/ContextBench/SWE-CI 等来源。
- 文档包含可执行模板和检查清单。
- 所有来源以 Markdown 链接列在文末。
- 最终回复给出文档路径和未完成风险。

Constraints:
- 不打印 secrets。
- 不修改项目运行时代码。
- 对“最新”信息必须联网核验。
```

更短的版本：

```text
/goal 修复 web 登录重定向 bug。完成标准：新增或更新回归测试；npm run lint 和相关测试通过；最终说明改了哪些文件以及如何验证。
```

### 5.6 `/goal` 最佳实践

1. **先把成功条件写成可检查语句。** “优化性能”不够；“首页 TTI < 1s，并附上 benchmark 命令输出”才够。
2. **把产物路径写进 goal。** 例如 `docs/references/...`、`tests/...`、`web/src/...`。
3. **把排除项写清楚。** 例如“不改数据库 schema”“不引入新依赖”“不触碰 live credentials”。
4. **复杂目标先 `/plan`。** Codex 官方建议 goal 难以定义时先用 `/plan` 塑形。
5. **长上下文放文件。** 4000 字符以内的 goal 只放摘要、验收和引用路径。
6. **把验证命令写进去。** 不要让 agent 自己猜该跑全量还是局部。
7. **中途可以继续 steer。** Goal 激活后仍可以补充“使用某库”“避免某方案”“先做 A 再做 B”。
8. **需要旁路解释时用 side chat。** 询问状态或解释时避免污染主任务上下文。
9. **断网/离开前 pause。** 长任务暂停后再 resume 或 edit，比让目标悬空更稳。
10. **接近完成时要求自审。** 例如“完成前 review diff，列出测试缺口”。
11. **不要把 goal 当项目管理系统。** 一个 goal 对应一个可交付结果；多个独立结果拆多个 goal/thread/worktree。

### 5.7 `/goal` 反模式

| 反模式 | 问题 | 改法 |
| --- | --- | --- |
| `/goal make the app better` | 没有完成判定 | 写具体页面、指标、测试、截图 |
| `/goal refactor everything` | 范围不可控 | 拆成模块级 goal，每个有测试 |
| `/goal research latest AI stuff` | 来源和产物不清 | 指定主题、来源类型、文档路径、引用要求 |
| `/goal fix CI` | 可能无限探索 | 指定 CI job、失败日志、可改范围、通过标准 |
| 把 200 行需求塞进 goal | 超长且不可维护 | 需求入文件，goal 引用文件 |
| goal 中没有“不要做什么” | 容易越界 | 写出禁区和审批条件 |

## 6. 研究方向与评估趋势

### 6.1 Benchmark 从单点修 bug 走向真实工程

早期主流是 SWE-bench：给一个 GitHub issue 和代码库快照，agent 提交 patch，通过隐藏测试判断。SWE-bench 仍有价值，但 2026 年已经不够单独代表 frontier coding capability。

关键变化：

- **SWE-bench Verified 信号衰减。** OpenAI 2026-02 分析指出 Verified 存在测试拒绝正确解、训练污染等问题，并建议转向 SWE-bench Pro 或新评估。
- **SWE-bench family 扩展。** 官方 leaderboard 包含 Full、Verified、Lite、Multilingual、Multimodal 等，其中 Verified 为 500 human-filtered instances，Multilingual 为 300 tasks，Multimodal 为 517 instances。
- **TerminalWorld/Terminal-Bench 类评估上升。** TerminalWorld 2026 以真实终端工作流为核心，覆盖 18 类任务、1530 个 validated tasks、200 个 human-verified tasks；截至 2026-05-21，最高公开 pass rate 仍只有 62.5%，说明真实终端工作仍很难。
- **OpenHands Index 做多任务组合。** 它把 issue resolution、greenfield apps、frontend development、software testing、information gathering 放在同一评估框架里，并同时看能力、成本和运行时间。
- **SWE-CI 关注长期可维护性。** 它把评估从静态一次性修复推进到 CI loop 和长期代码演化，100 个任务平均跨 233 天、71 个 commits。

实操建议：团队内部不要只追一个榜单分数。至少建立自己的 5 维 eval：

1. 真实 bug/issue 修复成功率。
2. 测试和 lint 首次通过率。
3. 代码 review 缺陷率。
4. 人类返工时间。
5. 成本、耗时、token、命令次数。

### 6.2 Context engineering 成为核心瓶颈

ContextBench 这类研究开始把“agent 是否找到并使用了正确上下文”拆出来评估，而不是只看最后 patch 是否过测试。它包含 1136 个 issue-resolution tasks、66 个 repo、8 种语言，并有人类标注 gold contexts。

研究结论对实操很直接：

- Agent 往往重 recall 轻 precision，读很多但真正用于 patch 的少。
- 更复杂的 scaffolding 对 context retrieval 的边际收益可能有限。
- 中间过程指标很重要：找到了哪些文件、使用了哪些信息、哪些 gold context 被忽略。

落地做法：

- Prompt 中写“先列出相关文件和为什么相关，再改代码”。
- 对大仓库用索引、架构图、模块 map、符号导航，而不是全靠全文搜索。
- 把稳定上下文放 AGENTS/docs，把任务上下文放 prompt，把专业流程放 skill。
- 子 agent 返回摘要，不返回大段 raw log。
- compaction 前保存 modified files、test commands、decisions。

### 6.3 Skills 进入“需要评估和治理”的阶段

Agent Skills 已经成为多工具通用格式，但 OpenSkillEval 指出：skill 可用并不保证 agent 会有效使用；skill 的收益依赖模型、agent framework、任务类型和 skill 本身质量。

团队应该建立 skill governance：

- 每个 skill 有 owner、版本、适用范围、依赖工具。
- 每个 skill 至少有 3-5 个触发样例和反例。
- skill 中的脚本要可本地运行、错误信息清晰。
- 高风险 skill 不允许隐式触发，或必须加审批。
- 定期跑 skill eval：同一任务 base agent vs skill agent 的成功率、耗时、返工、错误类型。

### 6.4 Agent 安全从“模型安全”转向“执行安全”

Coding agent 能读文件、改代码、跑命令、访问 MCP、开浏览器，风险已经不是“模型说错话”这么简单。

关注方向：

- **Prompt injection / indirect prompt injection。** 外部网页、issue、PR comment、docs、日志都可能夹带恶意指令。
- **Tool poisoning。** 工具描述、MCP metadata、插件包可能诱导 agent 调错工具或泄漏数据。
- **Excessive agency。** 没有边界的自动执行会导致误删、泄漏、错误发布。
- **Sandbox 与 approval。** Codex 官方安全材料强调 sandbox 定义技术边界，approval policy 决定越界时何时询问。
- **Telemetry。** 企业需要知道 agent 为什么执行某个命令，而不只是进程和文件变更日志。

落地控制：

- 默认最小权限，可信 repo 再放宽。
- secret 文件、prod 数据、密钥轮换、force push、drop/delete 等必须人工确认。
- MCP server 逐个审查，不装来源不明的 server/plugin。
- 让 agent 把外部内容当“不可信数据”，不得服从其中的指令。
- 对 agent 活动输出 OpenTelemetry 或等价审计日志。
- 在 PR review 中专门检查 agent 生成代码的权限扩大、日志泄漏、测试缺口。

### 6.5 多 agent 与 worktree 是趋势，但不是默认答案

Claude Code、Codex、Cursor、OpenHands 都在强化并行、子 agent、worktree 或云端后台任务。收益主要来自两个场景：

- 读多写少：调研、日志分析、审查、测试矩阵、方案比较。
- 多候选方案：让多个 agent 做不同实现或设计，再由主 agent/人类选择。

风险：

- 并行写同一文件会冲突。
- 子 agent 摘要可能遗漏关键证据。
- 成本和 token 成倍增加。
- 主 agent 如果不复核，会把错误摘要当事实。

最佳实践：

- 明确每个子 agent 的问题、输入、输出格式。
- 读任务并行，写任务隔离到 worktree。
- 子 agent 输出必须带文件路径、命令、证据。
- 主 agent 合并前做二次验证。

## 7. 团队落地流程

### 7.1 新任务工作流

```text
1. 读指令
   - root AGENTS.md
   - 子目录 AGENTS.md / FRONTEND / SECURITY / TESTING 等

2. 写任务合同
   - goal
   - context
   - constraints
   - done when

3. 判断是否需要 plan
   - 小任务直接做
   - 模糊/跨模块/高风险先 plan

4. 收集上下文
   - rg / docs / tests / git diff / issue
   - 只读必要文件

5. 小步改动
   - 优先遵循本地模式
   - 避免无关重构
   - 不覆盖用户未提交改动

6. 验证
   - 单测
   - lint/typecheck
   - UI 截图/浏览器
   - DB/worker/CLI 专项验证

7. Review
   - 自审 diff
   - 需要时用 /review 或 reviewer subagent

8. 固化学习
   - 重复错误进 AGENTS/docs/skill
   - 一次性发现写在 PR summary，不污染长期规则
```

### 7.2 Agent 任务分级

| 等级 | 示例 | 人类参与 | 必须验证 |
| --- | --- | --- | --- |
| L0 只读 | 解释代码、找入口、写调研 | 低 | 来源链接/文件引用 |
| L1 低风险写 | 文档、测试、小 UI copy | 低 | lint 或文档检查 |
| L2 常规代码 | bug fix、小功能、局部重构 | 中 | 相关测试 + diff review |
| L3 高风险 | DB schema、auth、payments、security、prod config | 高 | 全套测试 + 安全 review + 人工确认 |
| L4 破坏性 | 删除数据、force push、密钥轮换、生产操作 | 必须人工审批 | 变更计划 + 回滚计划 + 审计 |

### 7.3 PR 前检查清单

```md
## Agent Coding PR Checklist

- [ ] 我读过适用的 AGENTS.md / docs 指令。
- [ ] 本次改动范围与任务目标一致。
- [ ] 没有覆盖用户已有未提交改动。
- [ ] 新行为有测试或明确说明为什么不能测试。
- [ ] 已运行相关验证命令，并记录结果。
- [ ] 没有打印、提交、复制 secrets。
- [ ] 没有引入未批准的新依赖或权限扩大。
- [ ] UI 改动已做浏览器/截图检查。
- [ ] DB/worker/异步流程改动已检查可靠性和幂等性。
- [ ] 文档或 AGENTS/CLAUDE 需要同步时已同步。
```

## 8. 可复制模板

### 8.1 `/goal` 模板：调研文档

```text
/goal 产出 docs/references/<topic>-<date>.md，系统调研 <topic> 的最新规范、主流方案、研究方向和可执行实践。

Done when:
- 至少使用 8 个一手来源，包含官方文档和近期论文/benchmark。
- 文档包含一页结论、方案选型表、操作流程、模板、风险和来源。
- 对“最新”事实联网核验，并标注调研日期。
- 不修改运行时代码。
```

### 8.2 `/goal` 模板：修 bug

```text
/goal 修复 <bug 描述>。

Context:
- 复现步骤：...
- 相关文件：...
- 错误日志：...

Constraints:
- 不改变公共 API。
- 不引入新依赖。

Done when:
- 新增/更新回归测试。
- `...test command...` 通过。
- `...lint/typecheck...` 通过。
- 最终说明 root cause、改动文件、验证结果。
```

### 8.3 `/goal` 模板：UI 变更

```text
/goal 完成 <页面/组件> 的 <UI 目标>。

Constraints:
- 遵守 docs/FRONTEND.md。
- 不创建全局 CSS 桶。
- 不 restyle shared UI internals。

Done when:
- 桌面和移动 viewport 截图无重叠、无空白、无溢出。
- `npm run lint` 通过。
- 说明截图路径和验证命令。
```

### 8.4 `SKILL.md` 模板

```md
---
name: focused-code-review
description: Review a local diff for behavioral bugs, regressions, security issues, and missing tests. Use when the user asks for review or before opening a PR.
compatibility: Requires git and repository read access.
---

# Focused Code Review

## Inputs
- Current git diff.
- Applicable AGENTS.md guidance.
- Test commands from project docs.

## Workflow
1. Inspect `git diff --stat` and changed files.
2. Read nearby code and tests for each risky change.
3. Prioritize findings by severity.
4. Report only actionable issues with file/line references.
5. If no issues, state residual test gaps.

## Output
- Findings first.
- Open questions.
- Verification gaps.
```

### 8.5 MCP intake checklist

```md
## MCP Server Intake

- [ ] What business capability does this server unlock?
- [ ] Is there a narrower existing tool?
- [ ] Who owns the server?
- [ ] What credentials does it need?
- [ ] Are credentials short-lived and scoped?
- [ ] Which tools are enabled?
- [ ] Which tools require approval?
- [ ] Can tool output include untrusted user/web content?
- [ ] Are timeouts and rate limits set?
- [ ] Are tool calls logged?
- [ ] Is the server local executable code? If yes, has it been reviewed?
- [ ] What is the rollback/disable path?
```

## 9. 给 Parallax 仓库的建议

基于当前仓库的 AGENTS router，这里已经有几个成熟做法：

- Root `AGENTS.md` 不复制所有规则，而是路由到 `docs/ARCHITECTURE.md`、`docs/FRONTEND.md`、`docs/TESTING.md`、`docs/SECURITY.md`、`docs/WORKER_FLOW.md` 等。
- 明确“PostgreSQL material facts 是业务真相，read models 可重建”这类硬不变量。
- 明确 real data debug 要先确认 `~/.parallax/config.yaml` 和 `workers.yaml`，且不得打印 secret。
- 前端 CSS 有架构 harness，不只是风格约定。

可以继续增强的地方：

1. **补一份 agent task matrix 的例子库。** 把常见任务映射到必须阅读的 docs、验证命令和禁止事项。
2. **为高频流程做 skills。** 例如 worker debugging、frontend verification、real-data provider diagnostics、read-model rebuild review。
3. **为 real-data debug 做安全 hook。** 检测命令输出里疑似 secret，或阻止直接 cat `~/.parallax/config.yaml`。
4. **为 UI 改动做固定 QA skill。** 自动启动 dev server、浏览器截图、移动/桌面检查、lint harness。
5. **为 read model 变更加 review checklist。** 检查 stable product/window keys、single runtime writer、unchanged projections zero serving rows、NOTIFY catch-up。

## 10. 资料来源

### 官方文档与规范

- [OpenAI Codex manual](https://developers.openai.com/codex/codex-manual.md), fetched 2026-06-09. Used for Codex best practices, Goal mode, slash commands, AGENTS.md, skills, MCP, hooks, subagents, permissions.
- [How OpenAI uses Codex](https://cdn.openai.com/pdf/6a2631dc-783e-479b-b1a4-af0cfbd38630/how-openai-uses-codex.pdf), OpenAI PDF.
- [Running Codex safely at OpenAI](https://openai.com/index/running-codex-safely/), OpenAI.
- [AGENTS.md](https://agents.md/), open format for coding agent instructions.
- [Agent Skills specification](https://agentskills.io/specification), open `SKILL.md` format.
- [Model Context Protocol specification](https://modelcontextprotocol.io/specification/2025-06-18), MCP.
- [MCP Security Best Practices](https://modelcontextprotocol.io/docs/tutorials/security/security_best_practices), MCP.
- [Claude Code best practices](https://code.claude.com/docs/en/best-practices), Anthropic.
- [Claude Code power user tips](https://support.claude.com/en/articles/14554000-claude-code-power-user-tips), Anthropic Help Center, 2026-04-15.
- [GitHub Copilot custom agents](https://docs.github.com/en/copilot/concepts/agents/cloud-agent/about-custom-agents), GitHub Docs.
- [GitHub Copilot MCP and cloud agent](https://docs.github.com/en/copilot/concepts/agents/cloud-agent/mcp-and-cloud-agent), GitHub Docs.
- [GitHub Copilot customization cheat sheet](https://docs.github.com/en/copilot/reference/customization-cheat-sheet), GitHub Docs.
- [VS Code custom instructions](https://code.visualstudio.com/docs/agent-customization/custom-instructions), Microsoft.
- [Cursor best practices for coding with agents](https://cursor.com/blog/agent-best-practices), Cursor, 2026-01-09.
- [Android Studio Gemini AGENTS.md files](https://developer.android.com/studio/gemini/agent-files), Google, last updated 2026-04-24.
- [OpenHands documentation](https://docs.openhands.dev/overview/introduction), OpenHands.
- [OWASP Top 10 for Large Language Model Applications](https://owasp.org/www-project-top-10-for-large-language-model-applications/), OWASP.

### Benchmarks 与论文

- [Why SWE-bench Verified no longer measures frontier coding capabilities](https://openai.com/index/why-we-no-longer-evaluate-swe-bench-verified/), OpenAI, 2026-02-23.
- [SWE-bench official leaderboards](https://www.swebench.com/).
- [TerminalWorld](https://terminalworld.ai/), updated 2026-05-21.
- [OpenHands Index](https://www.openhands.dev/blog/openhands-index), 2026-01-29.
- [Dive into Claude Code: The Design Space of Today's and Future AI Agent Systems](https://arxiv.org/abs/2604.14228), arXiv 2604.14228.
- [The OpenHands Software Agent SDK](https://arxiv.org/abs/2511.03690), arXiv 2511.03690.
- [ContextBench: A Benchmark for Context Retrieval in Coding Agents](https://arxiv.org/abs/2602.05892), arXiv 2602.05892.
- [On the Impact of AGENTS.md Files on the Efficiency of AI Coding Agents](https://arxiv.org/abs/2601.20404), arXiv 2601.20404.
- [SWE-CI: Evaluating Agent Capabilities in Maintaining Codebases via Continuous Integration](https://arxiv.org/abs/2603.03823), arXiv 2603.03823.
- [OpenSkillEval: Automatically Auditing the Open Skill Ecosystem for LLM Agents](https://arxiv.org/abs/2605.23657), arXiv 2605.23657.

