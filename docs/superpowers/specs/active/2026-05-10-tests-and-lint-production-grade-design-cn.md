# Spec — Tests 与 Lint 生产级化（按 Harness Engineering 第九/十讲落地）

**Status**: Draft
**Date**: 2026-05-10
**Owner**: aaurix
**Related**:
- 参考：walkinglabs harness engineering lecture 9（why-agents-declare-victory-too-early）
- 参考：walkinglabs harness engineering lecture 10（why-end-to-end-testing-changes-results）
- 邻接：`docs/superpowers/specs/active/2026-05-10-providers-and-enforcement-design-cn.md`（架构强制器 enforcement 升级，本 spec 与之互补，不冲突）
- 既定治理：`docs/TESTING.md`、`docs/WORKFLOW.md:34-41`

---

## 1. Background

### 1.1 当前 lint / 测试链路（事实陈述）

- **后端 lint** 唯一一处配置在 `pyproject.toml:45-51`，启用规则集仅 `E F I UP B SIM`。无 mypy / pyright / bandit。无 `.pre-commit-config.yaml`，无 `.github/workflows/`。
- **后端测试** 全部在扁平 `tests/` 目录，95 个文件 / 563 测试 / ~18,900 行。`pyproject.toml:42-43` 仅声明 `testpaths = ["tests"]`，无 markers、无 addopts、无 strict-markers。
- **集成跳过机制** `tests/postgres_test_utils.py` 在 PG 不可达时自动 `pytest.skip()`，最近一次完整运行 `402 passed, 136 skipped`——`skipped` 占 ~25%，但当前 verification artefact 模板（`docs/superpowers/_templates/verification-template.md:33`）只要求粘贴 `N passed, M failed` 摘要行，对 skipped 无强制说明。
- **架构测试** `tests/test_src_domain_architecture.py`（13 个 AST 用例）+ `tests/test_harness_structure.py`（7 个文档结构用例）质量很高，与第十讲"架构规则机械化"完全对齐，是项目的现有亮点，需要保留并扩展。
- **golden 测试** `tests/golden/test_token_radar_corpus.py`（1 文件 / 112 行）端到端 ingest → projection 一段，但未触达 HTTP/WS/前端层。
- **真正端到端缺失**：`test_api_http.py` 与 `test_api_websocket.py` 走 FastAPI `TestClient`（同进程 ASGI），不是真跨进程；`docs/TESTING.md:23-26` 自己承认"UI / live-WebSocket flows that cannot be exercised by tests must be exercised manually"。
- **前端 lint** `web/package.json:6-12` 只跑 `tsc --noEmit + vite build + vitest run`。无 ESLint，无 Prettier，无 Biome。
- **前端测试** Vitest + jsdom + Testing Library，15 文件 / 86 用例，全部 mock 后端。无 Playwright，无浏览器级 e2e。
- **唯一聚合入口** `Makefile:23-29` 的 `make check` = `test + lint + compile`，三步顺序硬编码，无快慢路径区分。
- **完成判定** `docs/WORKFLOW.md:34-41` 列了 5 条 DoD 但全部依赖 agent 自跑自记，无任何工具链强制（pre-commit 不存在、CI 不存在、覆盖率门槛不存在）。

### 1.2 与 Harness Engineering 第九/十讲的差距

第九讲核心论点是"完成判定必须由 harness 独立执行，不能由生成 agent 自评"，第十讲核心论点是"组件边界缺陷只能被真实跨进程 e2e 抓到"。把两讲的 checklist 套到本仓库：

| Harness 要求 | 本仓库现状 | 差距 |
|---|---|---|
| 三层校验链：lint → unit/integration → e2e，前层不过禁开后层 | 三步顺序但无停车带；e2e 不存在 | 缺 e2e 层、缺顺序闸 |
| 错误消息含修复指导 | 架构测试做到了；其余 `assert response.status_code == 200` 类失败裸 fail | 部分对齐 |
| 生成与评估角色分离 | agent 自跑 `make check` 自写 verification | 未对齐 |
| 运行时信号 checklist（应用就绪 / 关键路径 / 副作用 / 资源清理） | 未结构化 | 未对齐 |
| 跨进程边界覆盖 | TestClient 同进程 / 前端全 mock 后端 | 未对齐 |
| 跳过用例的语义被严格管理 | silent skip，verification artefact 不要求 | 未对齐 |

---

## 2. Problem

`gmgn-twitter-intel` 的 SOP（spec → plan → verification）写得很认真，但**完成判定的执行权完全握在实现 agent 自己手里**。具体表现：lint 规则集偏窄、无类型检查、无 pre-commit、无覆盖率门槛、无真正的跨进程 e2e、PG 不可达时 25% 用例静默 skip、verification artefact 由实现者自写自评。这正是第九讲诊断的"提前交卷"高发结构，也是第十讲点名的"组件边界缺陷只能被真实边界抓到"的盲区结构。后果：跨层改动（schema 漂移、WS 协议变更、API 字段重命名）的回归无自动化防线，需依赖人工冒烟，回归窗口长。

---

## 3. First principles

本 spec 必须遵守的不可让步约束：

- **FP1：闸序约束。** lint+type 不绿则不进 unit+arch；unit+arch 不绿则不进 integration+e2e。任何一步失败必须立刻停止，错误消息直接告诉 agent 下一步该怎么修（第九讲第三层 + 第十讲"agent-friendly 错误"）。
- **FP2：单一证据来源。** 唯一被允许写入 verification artefact 的命令是 `make check-all`，其退出码与完整输出必须粘贴。"我本地跑了一下"在 DoD 中等同于"未跑"。
- **FP3：跳过 = 失败。** 默认情况下 PG/Docker 不可达必须 fail-loud。绕过通道是显式 `SKIP_INTEGRATION=1` / `SKIP_E2E=1`，启用后该次运行不可作为 verification 证据。
- **FP4：边界规则机械化优先于文档化。** 任何想写进 `docs/TESTING.md` 或 `docs/WORKFLOW.md` 的"必须"，先尝试写成 ruff 规则、mypy strict 项、ESLint 规则、AST 测试或 contract 测试；仅当机械化不可行时才落文档（第十讲"把架构规则变成可执行检查"）。
- **FP5：现有架构测试范式不动。** `tests/test_src_domain_architecture.py` 与 `tests/test_harness_structure.py` 的 AST/grep 风格是项目最佳实践，本 spec 在其基础上扩展（移入 `tests/architecture/`），不重写不替换。

---

## 4. Goals

每条目标都是可证伪的（带验证命令）。

- **G1：测试目录按金字塔分层完成迁移。** `tests/` 下出现 `unit/`、`integration/`、`e2e/`、`architecture/`、`contract/`、`golden/` 六个子目录，95 个现有文件按机械规则全部 git mv 到对应目录，零文件遗留在 `tests/` 根。验证：`find tests -maxdepth 1 -name 'test_*.py'` 返回空。
- **G2：`make check` 与 `make check-all` 双入口落地。** `make check`（快路径）运行 lint+type+unit+arch+contract，平均 < 10s 完成；`make check-all`（慢路径）追加 integration+e2e+coverage，平均 < 90s 完成。验证：`time make check` / `time make check-all`。
- **G3：lint 矩阵覆盖到位。** 后端 ruff 启用 `E F I UP B SIM S ASYNC RUF PERF PL`；后端 mypy strict 在 `domain/`、`platform/`、`cli.py` 全绿；前端 ESLint flat config（typescript-eslint strict + react-hooks + import + jsx-a11y recommended）+ Prettier 全绿；OpenAPI 漂移检查接入。验证：`make check` 退出 0。
- **G4：跨进程 e2e 黄金路径建立。** `tests/e2e/test_golden_path.py` 起 testcontainers Postgres + uvicorn subprocess + 真 httpx/websockets，断言 5 个运行时信号（就绪、ingest 写入、/recent 返回、WS 推送、清理）。验证：`uv run pytest tests/e2e/ -v` 至少 1 用例 passed。
- **G5：跳过用例语义被强制说明。** `pyproject.toml` 启用 `--strict-markers` 与 `--strict-config`，`verification-template.md` 增加 `Skipped tests` 强制字段（任何非 0 必须含理由与可接受性判断）。验证：模板 diff 含新表格；本 spec 自身的 verification artefact 含该字段。
- **G6：覆盖率门槛建立。** 后端 line ≥ 80% / branch ≥ 70%，由 `pytest --cov` + `coverage.fail_under = 80` 强制；CI 缺位下，`make check-all` 完成时打印门槛对比表。验证：在 baseline 不达标时 `make check-all` 退出非 0 并打印缺口。
- **G7：DoD 治理同步升级。** `docs/WORKFLOW.md:34-41` 与 `docs/TESTING.md:18-26` 改为引用 `make check-all` + verification 新模板字段；旧"UI/WS 手动验证"条款限定到本 spec 范围之外的真 UI 主观体验。验证：两份文档 diff 含新条款；架构测试 `tests/architecture/test_completion_gates.py` grep 关键短语断言两份文档同步。

---

## 5. Non-goals

- **N1：不引入 GitHub Actions 或任何云端 CI**（用户已选择本地 pre-commit + Makefile target 路径）。
- **N2：不引入 Playwright / Cypress 等浏览器级 e2e**（用户已选择仅后端跨进程 e2e；前端契约由 OpenAPI 同源生成 + Vitest 锁定）。
- **N3：不重写架构测试范式**（`tests/test_src_domain_architecture.py` 与 `tests/test_harness_structure.py` 仅迁移到新目录，不改逻辑）。
- **N4：不一次性做 mypy strict 全仓全绿**（domain/platform/cli 必须，其余包本 spec 仅设 override 并写入 TECH_DEBT；后续按包消化）。
- **N5：不改业务代码**。本 spec 只增/改测试基础设施、lint 配置、文档与 Makefile；除非 mypy strict 暴露真 bug，否则 `src/` 不动。
- **N6：不引入 mutation testing / 模糊测试**（生产级首版门槛不需要，未来可议）。
- **N7：不改造现有 `tests/postgres_test_utils.py` 的 skip 实现细节**，但其调用入口的语义被新 conftest 包装（详见 §7）。

---

## 6. Target architecture

### 6.1 测试金字塔与执行入口的关系

```
                ┌─ pre-commit ─┐
                │  ruff・ruff-fmt│        (装在 .git/hooks，仅闸 1)
                │  mypy・eslint  │
                └─────≤5s──────┘

make check    → │ 闸 1: lint+type │ + │ 闸 2: unit+arch+contract │
                                                                       (无外部依赖,~10s)

make check-all→ │ 闸 1 │ + │ 闸 2 │ + │ 闸 3: integration+e2e+coverage │
                                                                       (含 testcontainers,~90s)
```

闸序由 Makefile 的 `&&` 强制：前闸非零退出，后闸不执行。`make check-all` 是 verification artefact 唯一可接受的证据来源。

### 6.2 测试目录分层

```
tests/
├── __init__.py
├── conftest.py                           ← 新建：根 conftest，注册 markers + 共享 fixtures
├── unit/                                 ← ~40 文件：纯逻辑
│   ├── conftest.py                       ← 给本目录所有用例自动打 @pytest.mark.unit
│   └── test_*.py
├── integration/                          ← ~30 文件：真 Postgres
│   ├── conftest.py                       ← 自动 mark integration + 提供 e2e_postgres fixture 入口
│   └── test_*.py
├── e2e/                                  ← 新建
│   ├── conftest.py                       ← testcontainers PG + uvicorn subprocess fixture
│   └── test_golden_path.py               ← 第十讲核心：跨进程黄金路径
├── architecture/                         ← 现有 13+ AST 测试搬迁
│   ├── conftest.py                       ← 自动 mark architecture
│   ├── test_src_domain_architecture.py
│   ├── test_harness_structure.py
│   └── test_completion_gates.py          ← 新建：grep 校验 WORKFLOW.md/TESTING.md 同步
├── contract/                             ← 新建
│   ├── conftest.py                       ← 自动 mark contract
│   └── test_openapi_drift.py             ← 后端 app.openapi() ↔ docs/generated/openapi.json
├── golden/                               ← 现有保留（属 e2e 但语义独立）
│   └── test_token_radar_corpus.py
├── fixtures/                             ← 原样
├── factories.py / factories_token_radar.py / postgres_test_utils.py  ← 原样
```

**机械分类规则**（用于一次性 git mv 脚本，详见 plan）：

| 规则（按优先级排序） | 目标目录 |
|---|---|
| 路径 `tests/golden/*` | `tests/golden/` |
| 文件名匹配 `test_*architecture*` 或 `test_harness_structure*` 或 `test_project_structure*` | `tests/architecture/` |
| 内容 `import .*postgres_test_utils` 或 `from .*postgres_test_utils` | `tests/integration/` |
| 文件名匹配 `test_compose_*` 或 `test_docs_generated*` | `tests/integration/`（需 docker / Postgres） |
| 其余 | `tests/unit/` |

`tests/contract/` 与 `tests/e2e/` 起步为空，由本 spec 后续阶段填充。

### 6.3 Lint 矩阵

| 工具 | 范围 | 配置位置 | 入口 | 强制层级 |
|---|---|---|---|---|
| ruff (lint) | 全 Python | `pyproject.toml [tool.ruff.lint]` 扩 `S ASYNC RUF PERF PL` | `uv run ruff check .` | pre-commit + 闸 1 |
| ruff (format) | 全 Python | `pyproject.toml [tool.ruff.format]` 默认 | `uv run ruff format --check .` | pre-commit + 闸 1 |
| mypy | `src/` | `pyproject.toml [tool.mypy]` strict + override | `uv run mypy src` | 闸 1 |
| tsc | `web/src/` | `web/tsconfig.json`（已 strict） | `npm run typecheck` | 闸 1 |
| ESLint | `web/src/` | `web/eslint.config.js` flat | `npm run lint` | pre-commit + 闸 1 |
| Prettier | `web/` | `web/.prettierrc.json` | `npm run format:check` | pre-commit + 闸 1 |
| OpenAPI drift | 前后端契约 | `tests/contract/test_openapi_drift.py` | `make contract-check` | 闸 2 |
| coverage 门槛 | `src/` | `pyproject.toml [tool.coverage]` | `uv run pytest --cov` | 闸 3 |

**mypy 渐进白名单**（本 spec 必须 strict 通过的包）：

- `src/gmgn_twitter_intel/domains/` 全部子包
- `src/gmgn_twitter_intel/platform/`
- `src/gmgn_twitter_intel/cli.py`

其余包（`app/`、`integrations/`）通过 `[[tool.mypy.overrides]] disallow_untyped_defs = false` 临时放过，每条 override 在 `docs/TECH_DEBT.md` 立项跟踪。`no_implicit_optional = true`、`warn_unused_ignores = true` 等基础项保持全局严格。

### 6.4 e2e harness 形态

`tests/e2e/conftest.py` 提供三个 session-scope fixture：

- `e2e_postgres` —— 启动 `testcontainers.postgres.PostgresContainer("postgres:16-alpine")`，alembic upgrade head，yield DSN，会话末自动清理（ryuk）。
- `e2e_uvicorn(e2e_postgres)` —— `subprocess.Popen(["uv","run","python","-m","tests.e2e._uvicorn_entry","--port","0"], env={"GMGN_POSTGRES_DSN": dsn, ...})` 起一个**测试专用入口脚本** `tests/e2e/_uvicorn_entry.py`，该脚本调用项目内 `create_app(start_collector=False)`（`src/gmgn_twitter_intel/app/runtime/app.py:106`）后用 uvicorn 起服务。从子进程 stdout 解析端口，对 `/healthz` 与 `/readyz` 轮询 ≤ 30s，yield `f"http://127.0.0.1:{port}"`，会话末 SIGTERM。
- `e2e_writer(e2e_postgres)` —— 提供独立的 sidecar 写入接口（`subprocess.run` 启一个短命 Python，连同一个 DSN，通过项目 IngestService 写一条合成 mention 事件）。**写入与读取在物理上是两个进程**，这是本 e2e 的"跨进程边界"含义。

`test_golden_path.py` 必须断言以下 5 条（对齐第九讲 runtime checklist）：

1. `GET /readyz` 返回 200 且响应体声明 PG 探针通过（应用就绪）。
2. 通过 `e2e_writer` 写入 1 条合成 mention → 写入子进程退出码 0 且 PG 中 `evidence` 表新增至少 1 行（关键路径执行 + 副作用正确）。
3. `GET /api/recent?limit=10`（或当前等价路径，由 P5 实测确认）返回结果含步骤 2 的 mention（跨进程读路径）。
4. WebSocket 连接到 `/ws/live`（或当前等价路径，由 P5 实测确认），再通过 `e2e_writer` 写入一条 → WS 客户端在 5s 内收到 push event（异步副作用传播）。
5. 测试结束后 `e2e_postgres` 容器与 `e2e_uvicorn` 子进程均退出（资源清理）。

**关于注入路径的边界声明**：本 spec 不引入任何"测试专用 API endpoint"。事件注入走 sidecar writer 进程直接调 IngestService，不污染产线 API surface。本 spec 也不真实出网到 GMGN —— `start_collector=False` 把上游 WS 整段关闭。第十讲点名要拦的"跨组件缺陷"在这里指：DB schema 漂移、API response model 漂移、WS 序列化漂移、跨进程读写一致性。GMGN WS 协议本身的漂移由现有 `tests/test_direct_ws.py` 与 `docs/generated/ws-protocol.md` 一对契约管控，不在本 e2e 范围内。

### 6.5 OpenAPI 契约同源生成

- `scripts/regen_openapi.py` 启动一次 FastAPI app，把 `app.openapi()` 写到 `docs/generated/openapi.json`。
- `web/src/api/types.ts` 由 `npx openapi-typescript docs/generated/openapi.json -o web/src/api/types.ts` 生成，**纳入仓库**（不在 .gitignore），便于 review。
- `tests/contract/test_openapi_drift.py` 重新生成两份文件、对比与仓库内容是否一致；不一致 fail 并打印 diff，提示 `make regen-contract` 修复。
- 现有 `web/src/api/` 的手写客户端逐步切到 `types.ts` 的类型导入；本 spec 不强制全部切换，仅要求新增 API 调用使用 `types.ts`。

---

## 7. Conceptual data flow

```
agent edit
    └─→ pre-commit (闸 1 子集)
              └─→ make check  (闸 1 + 闸 2)        ← 日常快反馈
                       └─→ make check-all (闸 1+2+3) ← 写 verification artefact 必跑
                                  ├─→ pytest tests/unit + tests/architecture + tests/contract
                                  ├─→ pytest tests/integration  (需 PG;不可达 fail-loud + 自动 testcontainers)
                                  ├─→ pytest tests/e2e          (testcontainers + uvicorn subprocess)
                                  └─→ coverage report --fail-under=80
```

唯一新增"出仓"动作：`tests/e2e/conftest.py` 的 testcontainers 会调本机 docker daemon。容器在 ryuk 看护下随 pytest 退出而清理，不留状态。

---

## 8. Core models

本 spec 不引入数据库表或长期存储模型。引入的"软模型"如下：

- **TestLayer**（语义枚举）：`unit | integration | e2e | architecture | contract`。每个枚举值对应一个目录、一个 pytest marker、一个 Makefile sub-target、一个 `make check-all` 输出小节。
- **CheckGate**（语义枚举）：`gate1_lint_type | gate2_unit_arch_contract | gate3_integration_e2e_coverage`。Makefile 通过 `&&` 串联，前闸退出码非 0 立刻停止。
- **VerificationArtefactRow**（verification-template.md 新增字段）：见 §10.3。

---

## 9. Interface contracts

### 9.1 Makefile 公开 target

| Target | 行为 | 退出码语义 |
|---|---|---|
| `make check` | 闸 1 + 闸 2，无外部依赖 | 0 = 通过；非 0 = lint/type/unit/arch/contract 任一失败 |
| `make check-all` | 闸 1+2+3，PG 不可达自动起 testcontainers | 0 = 全闸通过且覆盖率达标；非 0 = 任一失败 |
| `make contract-check` | 重新生成 openapi.json 与 types.ts，对比仓库版本 | 0 = 同步；非 0 = 漂移 |
| `make regen-contract` | 强制重新生成两份契约文件 | 0 总成功，副作用是改文件 |
| `make lint` | 仅闸 1 | 0 / 非 0 |
| `make test-unit` / `test-integration` / `test-e2e` / `test-architecture` / `test-contract` | 仅运行某层 | 0 / 非 0 |
| `make coverage` | 输出当前 coverage 数字（不带 fail-under） | 0 总成功 |

旧 `make test`、`make lint`、`make compile`、`make check` 的契约必须保留向后兼容（旧 alias 不能消失，但可以重定向到新行为）。

### 9.2 pre-commit hook 公开行为

`.pre-commit-config.yaml` 包含 4 个 hook：`ruff`、`ruff-format`、`mypy`（仅本仓库白名单包）、`eslint --max-warnings=0`（仅 `web/src/`）。Hook 安装由 `make install-hooks` 一键完成。**不**安装 pytest/coverage 类 hook（避免 commit 慢）。

### 9.3 verification-template.md 强制字段

模板从描述性改为结构化必填。详见 §10.3。

---

## 10. Acceptance criteria

- **AC1（目录分层）：** WHEN 仓库 HEAD 在 spec 完成提交时 THEN `find tests -maxdepth 1 -name 'test_*.py'` SHALL 返回空，AND `ls tests/{unit,integration,e2e,architecture,contract,golden}/conftest.py` SHALL 全部存在。
- **AC2（marker 严格）：** WHEN 运行 `uv run pytest --collect-only -q` THEN 每个 collected item SHALL 至少带一个 `unit/integration/e2e/architecture/contract` marker，AND `pyproject.toml [tool.pytest.ini_options]` SHALL 含 `--strict-markers --strict-config` 与 5 个注册 marker。
- **AC3（快慢路径）：** WHEN 运行 `time make check` THEN 在干净缓存下 SHALL ≤ 15s 完成且退出 0；WHEN 运行 `time make check-all` THEN SHALL ≤ 120s 完成且退出 0（首次 testcontainers 镜像拉取除外，需在 verification artefact 注明）。
- **AC4（lint 升级）：** WHEN 运行 `uv run ruff check .` THEN SHALL 退出 0 且配置含 `S ASYNC RUF PERF PL`；WHEN 运行 `uv run ruff format --check .` THEN SHALL 退出 0；WHEN 运行 `uv run mypy src` THEN domain/platform/cli 包 SHALL 零 error；WHEN `cd web && npm run lint && npm run format:check` THEN SHALL 退出 0。
- **AC5（PG fail-loud）：** WHEN PG 不可达且未设 `SKIP_INTEGRATION=1` THEN `make check-all` SHALL 自动尝试 docker 起 testcontainers PG；起不动 SHALL 退出非 0 并在 stderr 打印至少 3 条修复指引（如何起 docker / 如何手动起 PG / 如何用 SKIP_INTEGRATION=1 跳过及其后果）。
- **AC6（e2e 黄金路径）：** WHEN 运行 `uv run pytest tests/e2e/test_golden_path.py -v` THEN SHALL 至少 1 用例 passed，AND 用例日志 SHALL 含 §6.4 的 5 条断言全部通过的证据。
- **AC7（OpenAPI 契约）：** WHEN 运行 `make contract-check` 在 docs/generated/openapi.json 与代码同步时 THEN SHALL 退出 0；WHEN 后端任意路由的 response model 字段被改而未运行 `make regen-contract` THEN SHALL 退出非 0 并打印 diff。
- **AC8（覆盖率门槛）：** WHEN 运行 `make check-all` 时 line coverage < 80% 或 branch coverage < 70% THEN SHALL 退出非 0；门槛达成 THEN stderr SHALL 打印 `coverage: line=X% branch=Y% (gate: 80/70)` 的对比行。
- **AC9（DoD 同步）：** WHEN spec 完成 THEN `docs/WORKFLOW.md` SHALL 引用 `make check-all` 而非旧三命令，AND `docs/_templates/verification-template.md` SHALL 含 `Coverage`、`Skipped tests`、`E2E golden path` 三个新强制小节，AND `tests/architecture/test_completion_gates.py` SHALL grep 验证两份文档与模板的同步。
- **AC10（自我证据）：** WHEN 本 spec 自身的 verification artefact 被写时 THEN SHALL 是第一个使用新模板的文件，且 `make check-all` 输出 + 退出码 0 SHALL 被完整粘贴。

---

## 11. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| 一次性 git mv 95 文件破坏 import path | 高 | 迁移脚本只动文件位置不改文件内容；`tests/__init__.py` 与各子目录 `__init__.py` 保证 pytest collection 不变；mv 后立即跑 `uv run pytest --collect-only` 验证 563 用例数量不变 |
| mypy strict 暴露真实 bug 拖慢 spec | 高 | domain/platform/cli 白名单内任一 bug 必修；其余包加 override 推迟。强制 spec 完成时 TECH_DEBT 含完整 override 清单 |
| testcontainers 在某些开发机 docker daemon 不可用 | 中 | 提供 `SKIP_E2E=1` 显式开关；该开关启用时 `make check-all` 退出码强制非 0 并打印警告，无法骗过 verification |
| coverage 80% 门槛初次不达标 | 中 | 实施 phase 6 时先量基线，若实测 < 80% 允许 spec 内临时把 `fail_under` 设为 baseline-2%，并把"补到 80%"作为 follow-up 写入 TECH_DEBT；阈值在 plan 里固化 |
| ruff `S`（bandit 子集）大面积 false positive | 中 | 已知吵闹规则（如 `S101 assert in tests`）在 `[tool.ruff.lint.per-file-ignores]` 对 `tests/**` 关闭；其他 false positive 一事一议，优先 `# noqa: S<code>` 局部抑制而非全局禁用 |
| pre-commit 被 `--no-verify` 绕过 | 中 | 不在 pre-commit 重复 `make check-all` 内容，让 pre-commit 仅做"快检查"；真正的"绿条"由 verification artefact 强制 `make check-all` 退出码与输出来兜底 |
| OpenAPI types 生成在前端 build 引入新依赖 | 低 | `openapi-typescript` 装为 dev-only；生成产物 `web/src/api/types.ts` 入 git，跑时 `npx` 调用 |
| 现有 verification artefact 突然不合规 | 低 | 旧 spec/plan 在 `completed/` 中不被本 spec 影响；新模板仅作用于 spec 完成后写的 verification 文件 |

---

## 12. Evolution path

**下一步可能扩展**（本 spec 不做，但留接口）：

- 引入 GitHub Actions：CI workflow 直接 `make check-all`，无须改 Makefile
- 引入 Playwright：仅追加 `tests/e2e/test_browser_*.py` 与 `web/playwright.config.ts`，testcontainers + uvicorn fixture 可被复用
- 引入 mutation testing：`mutmut` 或 `cosmic-ray`，作用于 `src/gmgn_twitter_intel/domains/*/services/`
- 引入差量覆盖率（diff-cover）：在 PR 模式下，新增代码覆盖率门槛收紧到 90%
- mypy 渐进消化非白名单包：每 sprint 摘掉 1-2 条 override，TECH_DEBT 计数下降到 0

**careful not to foreclose**：`make check-all` 的契约（"唯一证据来源"）不能被弱化。任何新加的快路径子命令，都必须最终被 `make check-all` 覆盖，避免回到"哪条命令算数"的混乱。

---

## 13. Alternatives considered

- **Alt A：引入 GitHub Actions CI** —— 这是第九讲推崇的"外部裁判"最完整实现。被拒因用户在澄清问题中明确选择"本地 pre-commit + Makefile（无云端）"，理由是零云端依赖、零成本。Spec 在 §12 evolution path 中保留升级通道。
- **Alt B：超大单 spec 全部一锅端 vs 拆 3 个 sub-spec** —— 拆分版本（先 tests 重排、再 lint、最后 e2e+CI）更原子化、更易回滚。被拒因用户明确选择单 spec。本 spec 通过 §15 phase 切分仍提供原子化执行路径，承载相同的"分阶段"价值。
- **Alt C：渐进迁移测试目录（新老并存）** —— 风险更低，但 split brain 风险高且常见永久化（实践案例多）。被拒因用户明确选择 one-shot git mv，且"重新梳理整个 tests"的措辞要求边界清晰。
- **Alt D：pyright 替代 mypy** —— pyright 更快、推断更接近 TS。被拒因 mypy strict + plugin 生态在 Pydantic / FastAPI 项目中更成熟，且与 ruff 的 `ANN` 规则协同更稳。
- **Alt E：Biome 替代 ESLint+Prettier** —— Biome 启动更快、配置更少。被拒因用户明确选择 ESLint flat 路径，且 React hooks 类规则（如 `react-hooks/exhaustive-deps`）目前仍以 ESLint plugin 实现最完整。
- **Alt F：FastAPI TestClient 算 e2e** —— 当前已在用，但属第十讲点名的"接口看起来对"盲区。被拒因 spec 显式目标是引入跨进程边界覆盖。

---

## 14. Boundaries

| Class | Behaviour |
|---|---|
| **Always** | spec 完成后，verification artefact 必须粘贴 `make check-all` 完整输出与退出码；新增/改动测试时必须放进对应分层目录；新增公开 API 路由时必须经 `make contract-check` 通过 |
| **Always** | mypy strict 白名单包内的类型错误必须修，不允许放进 override 推迟 |
| **Always** | 任何"必须"的规则尝试机械化优先于落文档；落文档时必须有架构测试 grep 校验 |
| **Ask first** | 若实测 coverage baseline 远低于 80%（< 60%）→ 与用户确认是否临时降低 `fail_under` 还是先补测试 |
| **Ask first** | 若 mypy strict 暴露 > 50 个真实 bug → 与用户确认是修复打包成 follow-up spec 还是本 spec 内消化 |
| **Ask first** | 若 testcontainers 在用户开发机 docker 不可用 → 与用户确认改方案（用 docker compose 替代 / 把 e2e 推到 CI evolution phase） |
| **Never** | 不引入 GitHub Actions / 任何云端 CI |
| **Never** | 不引入 Playwright / Cypress |
| **Never** | 不修改 `tests/test_src_domain_architecture.py` 或 `tests/test_harness_structure.py` 的断言逻辑（仅迁移路径） |
| **Never** | 不修改 `src/` 业务代码，除非 mypy strict 暴露真实 bug |
| **Never** | 不允许 verification artefact 用 "我本地跑过 ruff+pytest" 替代 `make check-all` 完整输出 |

---

## 15. Implementation phases（落进 plan 时按此切分，每 phase 一个 verification 小节）

| Phase | 主体 | 完成判定 |
|---|---|---|
| **P0 脚手架** | 创建 6 个空子目录与各自 conftest；根 conftest 注册 markers；`pyproject.toml` 加 `--strict-markers --strict-config` 与 marker 列表；Makefile 加新 target 占位 | 旧 `make check` 仍通过；新 `make test-unit` 等 target 跑空集合也退出 0 |
| **P1 大搬家** | 写 `scripts/migrate_tests_layout.py` 按 §6.2 规则 git mv 95 文件；适配各文件 import path（如有）；mv 后 `pytest --collect-only` 显示 563 用例不变 | 单 commit/单 PR，diff 几乎仅是 rename；`make check`（用旧规则集）仍通过 |
| **P2 lint 升级** | ruff 规则集扩；`ruff format`；ESLint flat config + Prettier；`web/package.json` 加 lint/format scripts；`.pre-commit-config.yaml` 落地；`make install-hooks` | `make check` 在新规则集下退出 0 |
| **P3 mypy 渐进** | `pyproject.toml [tool.mypy]` strict + override；逐包 fix domain/platform/cli 的真实类型问题；override 名单写入 `docs/TECH_DEBT.md` | `uv run mypy src` 退出 0 |
| **P4 OpenAPI 契约** | `scripts/regen_openapi.py`；前端 `npm i -D openapi-typescript`；`tests/contract/test_openapi_drift.py`；`make contract-check` / `make regen-contract` | `make contract-check` 退出 0 |
| **P5 e2e harness** | `pyproject.toml` dev 加 `testcontainers[postgres]`、`websockets`；`tests/e2e/conftest.py`；`tests/e2e/test_golden_path.py`；`make test-e2e` | `uv run pytest tests/e2e -v` 至少 1 用例 passed |
| **P6 覆盖率门槛 + DoD** | `pyproject.toml` `[tool.coverage]` + `pytest-cov`；`make coverage`；`coverage.fail_under` 设到 baseline 与 80% 之间合理值；`docs/_templates/verification-template.md` 改版；`docs/WORKFLOW.md`、`docs/TESTING.md` 同步；`tests/architecture/test_completion_gates.py` | `make check-all` 退出 0 + verification artefact 含本 spec 自身证据 |

每个 phase 在 plan 中各自一个章节、各自一段 acceptance commands、各自一段 rollback。

---

## 16. Open questions（spec 完成时全部需要 closed）

- **OQ1：** mypy override 的具体包名清单，要在 P3 实施时根据真实暴露的错误数量决定，spec 阶段先以"非 domain/platform/cli 默认 override"为契约。
- **OQ2：** `testcontainers` 镜像拉取首次耗时，需在 P5 实测后写入 verification artefact，决定是否需要在 README/SETUP 加 `docker pull postgres:16-alpine` 预热建议。
- **OQ3：** `make check-all` 在 P5 完成后的实测墙钟时间，决定 §10.AC3 的 ≤120s 数字是否需要 spec 修订上调（最大不超过 180s，否则 plan 需引入并行 pytest-xdist）。

OQ1 / OQ2 / OQ3 在对应 phase 的 verification 小节里 close，不阻塞 spec 进入 plan 阶段。
