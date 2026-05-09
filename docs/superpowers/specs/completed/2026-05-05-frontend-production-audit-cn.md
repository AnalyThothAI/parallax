# Frontend Production Audit - 2026-05-05

## 目标

本轮审计的目标不是继续补丁式修 UI，而是把前端容易反复改坏的根因拆开：

- 信息架构是否清晰：Radar、Live Tape、Signal Lab、Selected Token Detail 是否各自承担单一职责。
- 组件边界是否稳定：状态、查询、选择逻辑、展示逻辑是否被混在一起。
- 是否存在重复造轮子：窗口控件、过滤控件、未使用 UI 库、旧 API mock/type 是否残留。
- 是否存在兼容性代码：旧 bucket、旧 alert surface、半移除分支是否继续误导维护。
- 是否有生产级门禁：改坏前是否能在 typecheck/test/build 阶段失败。

## 第一性原理

前端的核心 job 不是把所有数据都展示出来，而是让交易员快速回答三个问题：

1. 现在什么 token 值得看。
2. 这个 token 的社交扩散是否真实、是否在加速、是否集中在少数账号。
3. 这条 signal chain 是否已经形成可行动的 driver/watch/discard 判断。

因此组件设计必须遵守 KISS：

- 一个时间窗口模型，只允许 `5m / 1h / 4h / 24h` 作为 radar 和 selected token detail 的产品窗口。
- 一个控件来源，窗口列表只能从共享常量产生。
- 一个 selected surface，token/detail/event/signal-chain 不能保留没有入口的旧分支。
- 一个编译门禁，未使用变量和未使用参数必须失败。

## 已落地修复

### 1. 移除未使用依赖

删除了前端包中没有任何 import 的依赖：

- `@tanstack/react-table`
- `@tanstack/react-virtual`
- `class-variance-authority`
- `clsx`
- `tailwind-merge`

这些依赖会制造错误预期，例如让维护者以为表格或虚拟列表已经进入架构，但实际 Token Radar 仍是本地组件实现。生产代码不应该保留这种暗示。

### 2. 打开 TypeScript unused 门禁

`web/tsconfig.json` 现在启用：

- `noUnusedLocals`
- `noUnusedParameters`

这会阻止死查询、死 helper、死组件继续留在主路径里。

### 3. 删除半移除的 account alerts 前端路径

删除了：

- `App.tsx` 中未读取的 `/api/account-alerts` React Query。
- `SelectedSignal` 中没有入口、也没有 drawer 渲染路径的 `alert` 分支。
- `web/src/api/types.ts` 中未使用的 `AccountAlertsData`。
- `App.test.tsx` 中不再被前端调用的 `/api/account-alerts` mock。

后端 `/api/account-alerts` 和 CLI 仍是独立产品面，没有被删除；本轮只清理前端已经不再支持的残留路径。

### 4. 测试从“随便点第一个 5m”改成按组件边界定位

旧测试用 `getAllByRole("button", { name: "5m" })[0]`，这种写法会掩盖重复窗口控件问题。现在改为在 radar surface 内定位 `5m`，让测试表达真实组件边界。

## 当前结构判断

### 符合生产方向的部分

- API contract 是显式 TypeScript type，不靠 `any` 泄洪。
- React Query 负责服务端状态，Zustand 负责本地交易员 UI 状态，方向合理。
- `OBSERVATION_WINDOWS` 已经成为窗口控件的唯一来源。
- `RadarControls` 复用后，顶栏/左侧/右侧重复窗口按钮的问题已经收敛到一个组件边界。
- `SignalLabPulse` 已有单独组件和测试，Twitter/X 跳转也进入组件职责内。

### 仍然存在的结构风险

1. `web/src/App.tsx` 仍然过大，约 1000 行，承担了查询编排、selected signal policy、layout composition、derived model 构造。它是未来最容易因为局部改动引发全局 UI 回归的文件。
2. `web/src/styles.css` 约 3000 行，仍是全局 CSS，很多 selector 在 breakpoint 中重复出现。重复本身有时合理，但现在缺少明确的 layout ownership，后续改 bottom deck、side rail、mobile task 时仍可能互相影响。
3. `web/src/api/types.ts` 约 700 行，聚合了全部 API shape。短期可接受，但继续增长后应按 domain 拆分为 token/radar/signal-lab/events。
4. 当前测试偏集成流，能抓产品行为，但对局部组件布局 contract 的防护还不够。视觉类 bug 需要补浏览器级断言，而不是只靠 jsdom。

## 建议的后续生产化拆分

不建议在同一轮里贸然大拆，因为当前 UI 已经稳定，应避免高风险重构。下一轮最小安全拆分顺序：

1. 抽出 `useCockpitQueries`：只负责 bootstrap/status/recent/token-flow/signal-lab 查询。
2. 抽出 `useSelectedSignalController`：只负责 token/event/signal-chain 的选择和 realignment。
3. 抽出 `buildLiveSignalTapeItems`：让 live tape model 变成可单测纯函数。
4. 按 domain 拆分 CSS：`layout.css`、`radar.css`、`detail.css`、`signal-lab.css`、`mobile.css`。
5. 增加浏览器级 layout smoke：desktop、narrow desktop、mobile 三个 viewport，检查 window controls 数量、bottom deck 高度、Signal Lab Pulse row 不重叠、外链存在。

## 验证门禁

本轮通过：

- `npm run typecheck`
- `npm test -- --run`
- `npm run build`
- `uv run ruff check .`
- `uv run python -m compileall src tests`
- `uv run pytest`

