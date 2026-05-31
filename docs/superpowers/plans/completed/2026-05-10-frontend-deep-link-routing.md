# Plan — 前端可深链路由化（Token Radar / Signal Lab / Watchlist）

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status**: Draft
**Date**: 2026-05-10
**Owning spec**: `docs/superpowers/specs/active/2026-05-10-frontend-deep-link-routing.md`
**Goal**: 把 Token Radar 二级页、Signal Lab 列表+Pulse 详情接入 react-router-dom，watchlist 链接化；新增 `GET /api/signal-lab/pulse/{candidate_id}` 让二级页可深链。
**Architecture**: 引入 `react-router-dom` v6，`<App>` 拆为 `<CockpitLayout>` + 三个 page component；Zustand 中的导航字段被 `useParams` / `useSearchParams` 取代；后端复用 `PulseRepository.candidate_by_id` + `SignalPulseService` 的 `_item` mapper 暴露单点端。
**Tech stack**: react-router-dom v6, zustand, @tanstack/react-query (现有), Vitest + RTL, FastAPI/Starlette (`api/http.py`).
**Worktree**: `.worktrees/feat-deep-link-routing/`
**Branch**: `feat/deep-link-routing`

## Pre-flight

- [ ] Spec is approved.
- [ ] Worktree exists at `.worktrees/feat-deep-link-routing/` and `git branch --show-current` matches `feat/deep-link-routing`. Create with: `git worktree add .worktrees/feat-deep-link-routing -b feat/deep-link-routing main`.
- [ ] Baseline `uv run ruff check .` passes.
- [ ] Baseline `uv run pytest` passes.
- [ ] Baseline `cd web && npm install && npm run test` passes.
- [ ] Baseline `cd web && npm run build` passes.

Known-failing baseline tests (none expected): —

---

## File-level edits（按 PR 切分前的索引）

### 后端（PR1）

#### `src/parallax/retrieval/signal_pulse_service.py`
- 行 100–139：把私有 `_item(row)` 整体重命名为 module-level `pulse_item_from_row`，**不保留旧名作别名**。模块内唯一 caller 在行 64 `[_item(row) for row in page_rows]` 改为 `[pulse_item_from_row(row) for row in page_rows]`。
- 在 `SignalPulseService` 上新增方法：
  - 新签名：`def candidate(self, *, candidate_id: str) -> dict[str, Any] | None: ...`
  - 行为：从 `self.pulse_repository.candidate_by_id(candidate_id)` 取 row；不存在返回 `None`；存在则同时校验 `_is_displayable(row)` 并返回 `pulse_item_from_row(row)`；若 row 存在但不可显示，返回 `None`（视同 404，避免泄露被屏蔽 candidate 的元数据）。

#### `src/parallax/api/http.py`
- 在行 466 之后（`signal_lab_pulse` 列表端之后、`harness_weights` 之前）新增 route：
  - 新签名：`@router.get("/signal-lab/pulse/{candidate_id}")` → `async def signal_lab_pulse_by_id(request: Request, candidate_id: str) -> JSONResponse`
  - 行为：
    1. `runtime = _authenticated_runtime(request)`
    2. 拒绝空 / 仅空白 candidate_id（返回 400 `{"ok": False, "error": "invalid_candidate_id", "field": "candidate_id"}`）。
    3. `with runtime.repositories() as repos: data = SignalPulseService(pulse=repos.pulse, harness=repos.harness).candidate(candidate_id=candidate_id)`
    4. `if data is None: return JSONResponse({"ok": False, "error": "not_found", "field": "candidate_id"}, status_code=404)`
    5. `return _json({"ok": True, "data": data})`
  - 与列表端一致：通过 `_authenticated_runtime` 共用 auth。当前 `api/http.py` 不配置 rate limit middleware；本端不引入新限流。

### 前端 PR2（router 基础设施 + Token 二级页）

#### `web/package.json`
- `dependencies` 新增：`"react-router-dom": "^6.30.0"`（v6 末版本；v7 改名 `react-router` 但 API 等价，本期固定 v6 保稳定）。
- 安装：`cd web && npm install react-router-dom@^6.30.0`。

#### `web/src/main.tsx`
- 行 17–23：在 `<QueryClientProvider>` 内嵌套 `<BrowserRouter>`：

  ```tsx
  import { BrowserRouter } from "react-router-dom";

  ReactDOM.createRoot(document.getElementById("root")!).render(
    <React.StrictMode>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </QueryClientProvider>
    </React.StrictMode>
  );
  ```

#### `web/src/components/CockpitLayout.tsx`（新建）
- 职责：从 `App.tsx` 抽出共享 chrome（顶部 bar、左侧 rail、center column 容器、`detail-task-panel` slot、mobile 底栏）。渲染 `<Outlet />` 作为 center column 的内容。
- 接收 props：`{ socket, watchlistRows, ... }`（即所有 chrome 需要的派生数据）。`pageTargetRef` 与 `activeView` 不再传入。
- **WS socket 的 `useIntelSocket` 仍在 `App.tsx` 顶层调用**，结果作为 prop 传入 `<CockpitLayout>`——`<CockpitLayout>` 自身不调 `useIntelSocket`，否则路由切换时 layout 重新挂载会断开订阅。
- 不持有路由判定逻辑——由内部 `<Routes>` 的 nested 结构决定渲染哪个 page component。

#### `web/src/components/LivePage.tsx`（新建）
- 职责：当前 `App.tsx:809` `activeView !== "signal_lab"` 分支里的雷达表格 + 底栏 deck。从 `App.tsx` 平移、按 props 接受所需数据。

#### `web/src/components/TokenTargetPage.tsx`
- 行 11–28（props 类型）：删除 `onBack` 与 `onWindowChange`、`onPostRangeChange`、`onPostSortModeChange`、`onStageSelect`、`onLoadMorePosts` 之外的旧导航 callback；引入新版本：把组件改成自取数据型——

  ```tsx
  // 新增 import
  import { useNavigate, useParams } from "react-router-dom";
  import { useQuery } from "@tanstack/react-query";
  import { useTokenTargetTimeline, useTokenTargetPosts } from "../api/useTokenTargetQueries";

  type RouteParams = { targetType: "Asset" | "CexToken"; targetId: string };

  export function TokenTargetPage() {
    const navigate = useNavigate();
    const { targetType, targetId } = useParams<RouteParams>();
    // 解析 target；从 URL 反序列化 → TargetRef
    // 自取 timeline + posts；保持现有 UI 渲染逻辑
    const onBack = () => navigate(-1);
    // ...其余渲染同现状
  }
  ```

  保留 `representativePosts` / `identityLine` / `marketLine` / `AuditMetric` / `StageTape` 内部辅助函数不动。

#### `web/src/App.tsx`
- 行 110–114：删除 `pageTargetRef` / `pageWindow` / `pagePostRange` / `pagePostSortMode` / `pageSelectedStageId` 五个 `useState`。`pageWindow` 改为 `TokenTargetPage` 内部 `useState`（当前其他四个亦然）。**已知行为变更**：现版每次进入 `/token/...` 时 `windowKey` 重置为 `"1h"`（不再跨次记忆）；这是路由化的预期代价，可接受。
- 行 252–290 一带：删除所有 `pageTargetRef` 相关派生。`pageTokenItems` 与 `pageQuery` 也删除——`TokenTargetPage` 自取。
- 行 465–478：删除 `openTokenPage`；列表行 `onOpenPage` 改为：

  ```tsx
  const navigate = useNavigate();
  // 列表 row 渲染处：
  <TokenRadarRow
    onOpenPage={(item) => navigate(`/token/${item.identity.target_type}/${item.identity.target_id}`)}
    // ...
  />
  ```

  注意：`item.identity.target_type` 必须为 `"Asset"` 或 `"CexToken"` 之一；遇到 `null` 跳过 navigate（保持现状不可点击体验）。
- 行 769–877：把整段 `cockpit-grid` 渲染改为 `<Routes>` 嵌套于 `<CockpitLayout>` 内：

  ```tsx
  <Routes>
    <Route element={<CockpitLayout {...chromeProps} />}>
      <Route index element={<LivePage {...liveProps} />} />
      <Route path="token/:targetType/:targetId" element={<TokenTargetPage />} />
      {/* signal-lab 路由在 PR3 接入 */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Route>
  </Routes>
  ```

  PR2 暂时把 `activeView === "signal_lab"` 分支保留为 `<Route index>` 内的条件渲染——这一段在 PR3 再切走，PR2 先不动 Signal Lab 任何用户路径。

#### `web/src/components/__tests__/TokenTargetPage.routing.test.tsx`（新建）
- 渲染 `<MemoryRouter initialEntries={["/token/Asset/asset%3Apepe"]}>` 内的 `<TokenTargetPage />`，stub `getApi`，断言：
  - `useTokenTargetTimeline` 被以 `target_type="Asset", target_id="asset:pepe"` 调用；
  - 返回按钮触发 `navigate(-1)`。

### 前端 PR3（Signal Lab + Pulse + Watchlist）

#### `web/src/api/useSignalPulseQueries.ts`（新建）
- 新签名：

  ```ts
  export function useSignalPulseList({ token, window, scope, status, handle, q, limit, cursor }: SignalPulseListArgs) { ... }
  export function useSignalPulseCandidate({ token, candidateId }: { token: string; candidateId: string | null }) {
    return useQuery({
      queryKey: ["signal-pulse-candidate", candidateId],
      queryFn: () => getApi<SignalPulseItem>("/api/signal-lab/pulse/" + encodeURIComponent(candidateId!), { token }),
      enabled: Boolean(token && candidateId),
      staleTime: 8_000
    });
  }
  ```

  把 `App.tsx:166` 的 list `useQuery` 也搬到 `useSignalPulseList` 内（保持当前 queryKey 与 staleTime 不变，避免缓存键漂移）。

#### `web/src/components/SignalLabPage.tsx`（新建）
- 职责：当前 `App.tsx:809` `activeView === "signal_lab"` 分支整段。
- 通过 `useSearchParams` 读 `scope` / `window` / `status` / `handle` / `q`；通过 `setSearchParams` 写。
- 保留现有 `<SignalLabWorkbench>` 渲染。

#### `web/src/components/PulseDetailPage.tsx`（新建）
- 职责：从 URL 读 `:candidateId` → `useSignalPulseCandidate` → 渲染既有 `<SignalLabInspector>`。
- candidate 不存在（404）→ 渲染 `<EmptyState message="Pulse 不存在或已被屏蔽" />`，保留 `<CockpitLayout>` 的 chrome 不变（spec 规定的 in-page 404）。

#### `web/src/store/useTraderStore.ts`
- 行 13：删除 `type ActiveView = "live" | "signal_lab"`。
- 行 32：删除 `activeView: ActiveView;`。
- 行 33–35：删除 `signalLabStatus` / `signalLabHandle` / `signalLabSearch` 三个字段。
- 行 53–56：删除 `setActiveView` / `setSignalLabStatus` / `setSignalLabHandle` / `setSignalLabSearch`。
- 行 76–79：删除对应初始值。
- 行 97–100：删除对应 setter 实现。
- 类型 `ActiveView` 在 `web/src/api/types.ts` 若有定义，一并删除。

#### `web/src/App.tsx`
- 行 76–79：删除 4 个 `useTraderStore((s) => s.activeView/signalLabStatus/signalLabHandle/signalLabSearch)` selector。
- 行 100：删除 `setSignalLabSearch` selector。
- 行 134：`activeSignalLabHandle` 不再从 store 派生；如果 sidebar 仍需要"当前选中 handle"高亮，从 `useSearchParams().get("handle")` 派生。
- 行 166–175：list `useQuery` 整段搬到 `useSignalPulseList` hook（参数源改为 URL）。
- 行 353、445、527、658–660、769、809–823 等所有 `activeView` 引用：移除（路由匹配代替）。
- 行 505–518 `focusWatchHandle`：整段删除。
- 行 781–799 watchlist sidebar：

  ```tsx
  import { Link } from "react-router-dom";
  // ...
  <Link
    to={"/signal-lab?handle=" + encodeURIComponent(row.handle)}
    className={location.pathname === "/signal-lab" && currentHandleParam === row.handle ? "active" : ""}
  >
    @{row.handle}
  </Link>
  ```
- 行 658–660 RailButton：`<RailButton ... onClick={() => navigate("/")} />` 与 `<RailButton ... onClick={() => navigate("/signal-lab")} />`，`active` 由 `useLocation().pathname` 判定。
- `<Routes>` 扩展：

  ```tsx
  <Route path="signal-lab" element={<SignalLabPage />}>
    <Route path="pulse/:candidateId" element={<PulseDetailPage />} />
  </Route>
  ```

#### `web/src/components/__tests__/SignalLabPage.routing.test.tsx`（新建）
- 测试：`<MemoryRouter initialEntries={["/signal-lab?handle=toly&status=token_watch"]}>` 渲染后，`useSignalPulseList` 被以 `handle="toly", status="token_watch"` 调用。

#### `web/src/components/__tests__/PulseDetailPage.routing.test.tsx`（新建）
- 测试 1（正常）：`/signal-lab/pulse/cand-xyz` + stub `getApi` 返回 SignalPulseItem，断言 `<SignalLabInspector>` 渲染该 candidate 字段。
- 测试 2（404）：stub `getApi` 抛 404，断言 in-page 404 文本可见、`<CockpitLayout>` chrome 仍可见。

### Storage / migrations

无。本计划不涉及任何 schema、迁移、回填。

### Tests

#### 后端（PR1）
- `tests/test_signal_pulse_service.py::test_candidate_returns_full_item` — 新增；FakePulseRepository 增加 `candidate_by_id` 方法返回 row，断言 `SignalPulseService.candidate(candidate_id="cand-1")` 返回的对象与 list `_item(row)` 完全一致。
- `tests/test_signal_pulse_service.py::test_candidate_returns_none_when_missing` — 新增；`candidate_by_id` 返回 `None`，断言 `SignalPulseService.candidate(candidate_id="ghost")` 返回 `None`。
- `tests/test_signal_pulse_service.py::test_candidate_returns_none_when_blocked` — 新增；`candidate_by_id` 返回 row 但 `pulse_status="blocked_low_information"`，断言 `SignalPulseService.candidate(...)` 返回 `None`。
- `tests/test_api_http.py::test_api_signal_pulse_by_id_returns_item` — 新增；插入一条 displayable candidate（沿用 `tests/test_pulse_repository.py` 的 fixture 风格）后 GET `/api/signal-lab/pulse/{id}`，断言 200 + `data.candidate_id`。
- `tests/test_api_http.py::test_api_signal_pulse_by_id_returns_404_when_missing` — 新增；GET `/api/signal-lab/pulse/ghost-id`，断言 404 + `error="not_found"`。
- `tests/test_api_http.py::test_api_signal_pulse_by_id_rejects_blank` — 新增；GET `/api/signal-lab/pulse/%20`，断言 400 + `error="invalid_candidate_id"`。
- `tests/test_api_http.py::test_api_signal_pulse_by_id_requires_auth` — 新增；GET 不带 `Authorization` 头，断言 401（与 `_authenticated_runtime` 现有契约一致）。

#### 前端 PR2
- `web/src/components/__tests__/TokenTargetPage.routing.test.tsx`（见上）。
- `web/src/App.test.tsx::renders LivePage at root`（修改既有；用 `<MemoryRouter>` 包装）。

#### 前端 PR3
- `web/src/components/__tests__/SignalLabPage.routing.test.tsx`（见上）。
- `web/src/components/__tests__/PulseDetailPage.routing.test.tsx`（见上）。
- `web/src/components/__tests__/Watchlist.linkify.test.tsx` — 新增：渲染 sidebar，断言 watchlist row 是 `<a href="/signal-lab?handle=toly">` 且无 `onClick` 副作用；点击触发路由变化。

---

## PR breakdown（每 PR 走 TDD：先红、再绿、再 commit）

### PR1 — `feat: deep-link signal pulse candidate api`

依赖：无。完全后端 PR；前端零改动；可独立合并并部署。

**Files**:
- Modify: `src/parallax/retrieval/signal_pulse_service.py:15-152`
- Modify: `src/parallax/api/http.py:466`（在该位置之后插入新 route）
- Test: `tests/test_signal_pulse_service.py`
- Test: `tests/test_api_http.py`

#### Task 1.1 — Service 层：先写失败测试

- [ ] **Step 1**：写失败测试 `test_candidate_returns_full_item`（`tests/test_signal_pulse_service.py`）。

  ```python
  def test_candidate_returns_full_item() -> None:
      row = _candidate_row(
          "cand-1",
          pulse_status="token_watch",
          verdict="token_watch",
          market_context_json={"market_status": "fresh"},
      )
      pulse = FakePulseRepository()
      pulse.candidate_rows = {"cand-1": row}  # Fake 新字段，下一步加

      result = SignalPulseService(pulse=pulse, harness=None).candidate(candidate_id="cand-1")

      assert result is not None
      assert result["candidate_id"] == "cand-1"
      assert result["pulse_status"] == "token_watch"
      assert result["thesis_json"]["summary_zh"] == "PEPE 社交热度显著上升。"
      assert result["playbooks"] == []
  ```

- [ ] **Step 2**：跑测试，确认失败。

  ```bash
  uv run pytest tests/test_signal_pulse_service.py::test_candidate_returns_full_item -v
  ```
  Expected: FAIL with `AttributeError: 'SignalPulseService' object has no attribute 'candidate'` 或 `FakePulseRepository` 缺方法。

- [ ] **Step 3**：在 `tests/test_signal_pulse_service.py::FakePulseRepository` 加方法（行 60 附近）：

  ```python
  def candidate_by_id(self, candidate_id: str) -> dict[str, Any] | None:
      return getattr(self, "candidate_rows", {}).get(candidate_id)
  ```

  并把 `__init__` 加 `self.candidate_rows: dict[str, dict[str, Any]] = {}`。

- [ ] **Step 4**：在 `src/parallax/retrieval/signal_pulse_service.py`：

  1. 把 `def _item(row: ...)` 整体改名为 `def pulse_item_from_row(row: ...)`（行 100）。
  2. 把同模块行 64 的 `[_item(row) for row in page_rows]` 改为 `[pulse_item_from_row(row) for row in page_rows]`。
  3. 在 `SignalPulseService` 类内新增方法：

  ```python
  def candidate(self, *, candidate_id: str) -> dict[str, Any] | None:
      row = self.pulse_repository.candidate_by_id(candidate_id)
      if row is None:
          return None
      if not _is_displayable(row):
          return None
      return pulse_item_from_row(row)
  ```

- [ ] **Step 5**：跑测试，确认通过。

  ```bash
  uv run pytest tests/test_signal_pulse_service.py::test_candidate_returns_full_item -v
  ```
  Expected: PASS.

- [ ] **Step 6**：再加两个失败/边界用例：

  ```python
  def test_candidate_returns_none_when_missing() -> None:
      pulse = FakePulseRepository()
      result = SignalPulseService(pulse=pulse).candidate(candidate_id="ghost")
      assert result is None


  def test_candidate_returns_none_when_blocked() -> None:
      row = _candidate_row(
          "cand-blocked",
          pulse_status="blocked_low_information",
          verdict="blocked_low_information",
          market_context_json={},
      )
      pulse = FakePulseRepository()
      pulse.candidate_rows = {"cand-blocked": row}
      result = SignalPulseService(pulse=pulse).candidate(candidate_id="cand-blocked")
      assert result is None
  ```

- [ ] **Step 7**：跑全 service 测试套件。

  ```bash
  uv run pytest tests/test_signal_pulse_service.py -v
  ```
  Expected: 所有用例 PASS。

- [ ] **Step 8**：commit。

  ```bash
  git add src/parallax/retrieval/signal_pulse_service.py tests/test_signal_pulse_service.py
  git commit -m "feat(retrieval): add SignalPulseService.candidate single-item lookup"
  ```

#### Task 1.2 — HTTP 层：先写失败测试

- [ ] **Step 1**：在 `tests/test_api_http.py` 末尾新增（参考行 467 既有用例的 fixture 与 client 设置）：

  ```python
  def test_api_signal_pulse_by_id_returns_404_when_missing(tmp_path):
      app = create_app(settings=make_settings(tmp_path), start_collector=False)
      with TestClient(app) as client:
          response = client.get(
              "/api/signal-lab/pulse/ghost-id",
              headers={"Authorization": "Bearer secret"},
          )
      assert response.status_code == 404
      assert response.json() == {"ok": False, "error": "not_found", "field": "candidate_id"}


  def test_api_signal_pulse_by_id_rejects_blank(tmp_path):
      app = create_app(settings=make_settings(tmp_path), start_collector=False)
      with TestClient(app) as client:
          response = client.get(
              "/api/signal-lab/pulse/%20",
              headers={"Authorization": "Bearer secret"},
          )
      assert response.status_code == 400
      assert response.json() == {"ok": False, "error": "invalid_candidate_id", "field": "candidate_id"}


  def test_api_signal_pulse_by_id_requires_auth(tmp_path):
      app = create_app(settings=make_settings(tmp_path), start_collector=False)
      with TestClient(app) as client:
          response = client.get("/api/signal-lab/pulse/cand-1")
      assert response.status_code == 401
  ```

- [ ] **Step 2**：跑测试，确认失败（route 不存在 → 404 但消息不匹配；或 405）。

  ```bash
  uv run pytest tests/test_api_http.py -k signal_pulse_by_id -v
  ```

- [ ] **Step 3**：在 `src/parallax/api/http.py` 行 466 之后插入：

  ```python
      @router.get("/signal-lab/pulse/{candidate_id}")
      async def signal_lab_pulse_by_id(
          request: Request,
          candidate_id: str,
      ) -> JSONResponse:
          runtime = _authenticated_runtime(request)
          normalized = (candidate_id or "").strip()
          if not normalized:
              return JSONResponse(
                  {"ok": False, "error": "invalid_candidate_id", "field": "candidate_id"},
                  status_code=400,
              )
          with runtime.repositories() as repos:
              data = SignalPulseService(pulse=repos.pulse, harness=repos.harness).candidate(
                  candidate_id=normalized,
              )
          if data is None:
              return JSONResponse(
                  {"ok": False, "error": "not_found", "field": "candidate_id"},
                  status_code=404,
              )
          return _json({"ok": True, "data": data})
  ```

- [ ] **Step 4**：跑测试，确认前 3 用例通过。

  ```bash
  uv run pytest tests/test_api_http.py -k signal_pulse_by_id -v
  ```

- [ ] **Step 5**：增加 hit-path 用例 `test_api_signal_pulse_by_id_returns_item`——构造一条真实 displayable candidate 写入 DB 后再读：

  ```python
  def test_api_signal_pulse_by_id_returns_item(tmp_path):
      settings = make_settings(tmp_path)
      app = create_app(settings=settings, start_collector=False)
      _seed_displayable_candidate(settings, candidate_id="cand-real")  # 见辅助
      with TestClient(app) as client:
          response = client.get(
              "/api/signal-lab/pulse/cand-real",
              headers={"Authorization": "Bearer secret"},
          )
      assert response.status_code == 200
      data = response.json()["data"]
      assert data["candidate_id"] == "cand-real"
      assert data["pulse_status"] in {"trade_candidate", "token_watch", "theme_watch", "risk_rejected_high_info"}
  ```

  `_seed_displayable_candidate(settings, candidate_id)` 在 `tests/test_api_http.py` 内新增（不导出）。实现：用 `make_settings` 已建好的 DB 连接，`PulseRepository.upsert_candidate(...)`（见 `src/parallax/storage/pulse_repository.py:354`）插入一条 `pulse_status="token_watch"`、`verdict="token_watch"`、必填 `window="1h"`、`scope="all"`、`thesis_json={...}` 的 row，与 `tests/test_signal_pulse_service.py::_candidate_row` 同形。

- [ ] **Step 6**：跑全 http 测试套件 + ruff。

  ```bash
  uv run ruff check src/parallax/api/http.py
  uv run pytest tests/test_api_http.py -v
  ```
  Expected: 全 PASS。

- [ ] **Step 7**：commit。

  ```bash
  git add src/parallax/api/http.py tests/test_api_http.py
  git commit -m "feat(api): GET /api/signal-lab/pulse/{candidate_id} for deep-link"
  ```

#### Task 1.3 — Verification（PR1）

- [ ] `uv run ruff check .` — PASS
- [ ] `uv run pytest` — PASS（全套）
- [ ] `uv run python -m compileall src tests` — PASS
- [ ] curl smoke：

  ```bash
  uv run parallax ops serve &
  sleep 2
  curl -s -H "Authorization: Bearer dev" http://127.0.0.1:8765/api/signal-lab/pulse/non-existent | jq
  # 期望: {"ok": false, "error": "not_found", "field": "candidate_id"}
  ```

- [ ] 推送 PR；PR description 列出 3 个 acceptance 用例。

---

### PR2 — `feat: react-router-dom + token target page deep-link`

依赖：PR1 已合并（前端调用已可工作；但 PR2 不依赖 PR1 的端点，可独立 review）。

**Files**:
- Modify: `web/package.json`
- Modify: `web/src/main.tsx:1-24`
- Create: `web/src/components/CockpitLayout.tsx`
- Create: `web/src/components/LivePage.tsx`
- Modify: `web/src/components/TokenTargetPage.tsx:1-204`
- Modify: `web/src/App.tsx:110-114, 252-290, 465-478, 769-877`
- Test: `web/src/components/__tests__/TokenTargetPage.routing.test.tsx`
- Test: `web/src/App.test.tsx`

#### Task 2.1 — 安装依赖、`<BrowserRouter>` 装入

- [ ] **Step 1**：安装。

  ```bash
  cd web && npm install react-router-dom@^6.30.0
  ```

- [ ] **Step 2**：修改 `web/src/main.tsx`：

  ```tsx
  import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
  import React from "react";
  import ReactDOM from "react-dom/client";
  import { BrowserRouter } from "react-router-dom";
  import { App } from "./App";
  import "./styles.css";

  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { refetchOnWindowFocus: false, retry: 1, staleTime: 8_000 }
    }
  });

  ReactDOM.createRoot(document.getElementById("root")!).render(
    <React.StrictMode>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </QueryClientProvider>
    </React.StrictMode>
  );
  ```

- [ ] **Step 3**：在 `web/src/test/setup.ts` 中确保 `MemoryRouter` 可用——通常无需改动，若 `App.test.tsx` 报 "useNavigate within Router"，把现有 test 包一层 `<MemoryRouter>`：

  ```tsx
  import { MemoryRouter } from "react-router-dom";
  // 现有 render(<App />) 改为 render(<MemoryRouter><App /></MemoryRouter>)
  ```

- [ ] **Step 4**：跑测试 + build。

  ```bash
  cd web && npm run test && npm run build
  ```
  Expected: PASS。如失败仅因测试缺 Router wrap，按 Step 3 修补。

- [ ] **Step 5**：commit。

  ```bash
  git add web/package.json web/package-lock.json web/src/main.tsx web/src/App.test.tsx
  git commit -m "chore(web): add react-router-dom + BrowserRouter shell"
  ```

#### Task 2.2 — 抽 `<CockpitLayout>` + `<LivePage>`

- [ ] **Step 1**：写失败测试 `web/src/components/__tests__/LivePage.routing.test.tsx`：

  ```tsx
  import { render, screen } from "@testing-library/react";
  import { MemoryRouter, Routes, Route } from "react-router-dom";
  import { LivePage } from "../LivePage";

  it("renders radar table at root route", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={<LivePage tokenItems={[]} liveItems={[]} {/* ... */} />} />
        </Routes>
      </MemoryRouter>
    );
    expect(screen.getByLabelText(/token radar/i)).toBeInTheDocument();
  });
  ```

- [ ] **Step 2**：跑测试，确认失败（`LivePage` 不存在）。

  ```bash
  cd web && npm run test -- LivePage.routing
  ```

- [ ] **Step 3**：创建 `web/src/components/LivePage.tsx`，从 `App.tsx:809-877` 把"非 signal_lab"分支整段平移；接受所需 props（不读 store 的 `activeView`，因为路由已决定）。保持 `<TokenRadarTable>` 的 `onOpenPage` 回调签名为 `(item: TokenFlowItem) => void`，由父组件注入 `useNavigate`。

- [ ] **Step 4**：创建 `web/src/components/CockpitLayout.tsx`，把 `App.tsx:704-943` 的外壳（侧栏、center column 容器、detail-task-panel slot、mobile 底栏、notification drawer）平移；center column 内部渲染 `<Outlet />`。

  **Props 接口（`CockpitLayoutProps`）**——把 `App.tsx` 里被外壳读到的派生值提升为显式 props，**不要**在 layout 里再读 store：

  ```tsx
  type CockpitLayoutProps = {
    socket: ReturnType<typeof useIntelSocket>;
    watchlistRows: WatchlistRow[];
    notifications: Notification[];
    notificationDrawerOpen: boolean;
    onToggleNotificationDrawer: () => void;
    mobileTask: MobileTask;
    onMobileTaskChange: (task: MobileTask) => void;
    detailPanelSlot: ReactNode;  // 右栏渲染什么由路由内子组件决定，外壳不参与
  };
  ```

  其余 sidebar 内部 widgets（scope/decisions/watchlist）保持现有渲染。**`App.tsx` 在 PR2 末态退化为 router 的"装配台"，把这些值算好后传给 `<CockpitLayout>`**——`liveProps` 同理：把当前 `<LivePage>` 用到的 token-radar 数据派生从 `App.tsx` 里抽出，作为显式 props 传入。具体字段对照 `App.tsx:704-943` 现有读到的局部变量逐一搬迁。

- [ ] **Step 5**：跑测试与 build。

  ```bash
  cd web && npm run test -- LivePage CockpitLayout && npm run build
  ```
  Expected: PASS。

- [ ] **Step 6**：commit。

  ```bash
  git add web/src/components/CockpitLayout.tsx web/src/components/LivePage.tsx web/src/components/__tests__/LivePage.routing.test.tsx
  git commit -m "refactor(web): extract CockpitLayout and LivePage from App"
  ```

#### Task 2.3 — `<TokenTargetPage>` 路由化（自取数据）

- [ ] **Step 1**：写失败测试 `web/src/components/__tests__/TokenTargetPage.routing.test.tsx`：

  ```tsx
  import { render, screen, waitFor } from "@testing-library/react";
  import { MemoryRouter, Routes, Route } from "react-router-dom";
  import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
  import { TokenTargetPage } from "../TokenTargetPage";
  import * as client from "../../api/client";
  import { vi } from "vitest";

  it("calls target-social-timeline with URL params", async () => {
    const getApi = vi.spyOn(client, "getApi").mockResolvedValue({ ok: true, data: STUB_TIMELINE });
    const qc = new QueryClient();
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/token/Asset/asset%3Apepe"]}>
          <Routes>
            <Route path="/token/:targetType/:targetId" element={<TokenTargetPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );
    await waitFor(() => {
      expect(getApi).toHaveBeenCalledWith("/api/target-social-timeline", expect.objectContaining({
        params: expect.objectContaining({ target_type: "Asset", target_id: "asset:pepe" })
      }));
    });
  });
  ```

  `STUB_TIMELINE` 写一份最小满足 `TokenSocialTimelineData` 类型的 fixture（必填字段：`stages: []`、`posts: []`、`summary: { posts: 0, authors: 0 }`、`token` 引用一个 `TokenFlowItem`-shape 对象）。沿用现有 `web/src/components/SignalLabPulse.test.tsx` 的 fixture 构造风格。

- [ ] **Step 2**：跑测试，确认失败。

- [ ] **Step 3**：把 `web/src/components/TokenTargetPage.tsx` 改为自取数据型组件——保留所有内部辅助函数与 JSX，仅替换数据来源：

  ```tsx
  import { useNavigate, useParams } from "react-router-dom";
  import { useState } from "react";
  import { useTokenTargetTimeline, useTokenTargetPosts, mergeTokenPostPages } from "../api/useTokenTargetQueries";
  import { useTraderStore } from "../store/useTraderStore";
  // ...

  type RouteParams = { targetType: string; targetId: string };
  const VALID_TARGET_TYPES = new Set(["Asset", "CexToken"]);

  export function TokenTargetPage() {
    const navigate = useNavigate();
    const params = useParams<RouteParams>();
    const token = useTraderStore((s) => s.token);
    const scope = useTraderStore((s) => s.scope);

    // 校验 URL 参数：targetType 必须是后端枚举之一，否则在页内渲染 404，避免发出注定 400 的请求
    if (!params.targetType || !VALID_TARGET_TYPES.has(params.targetType) || !params.targetId) {
      return (
        <section className="token-target-page" aria-label="Token audit page (not found)">
          <button className="ghost-icon-button" type="button" onClick={() => navigate("/")} aria-label="Back to Live">
            <ArrowLeft aria-hidden /> <span>Live</span>
          </button>
          <div className="empty-state">Token 不存在或链接已失效</div>
        </section>
      );
    }
    const target = { target_type: params.targetType as "Asset" | "CexToken", target_id: params.targetId };

    const [windowKey, setWindowKey] = useState<WindowKey>("1h");
    const [postRange, setPostRange] = useState<TokenPostRange>("current_window");
    const [postSortMode, setPostSortMode] = useState<TokenPostSortMode>("recent");
    const [selectedStageId, setSelectedStageId] = useState<string | null>(null);
    const [watchedPostsOnly, setWatchedPostsOnly] = useState(false);
    const [hideDuplicateClusters, setHideDuplicateClusters] = useState(false);

    const timelineQuery = useTokenTargetTimeline({ token, target, window: windowKey, scope });
    const postsQuery = useTokenTargetPosts({ token, target, window: windowKey, scope, range: postRange, sort: serverSort(postSortMode), limit: 24 });
    const posts = mergeTokenPostPages(postsQuery.data?.pages);

    // 沿用既有 JSX；onBack 改为 navigate(-1)
    const onBack = () => navigate(-1);

    // ... 以下 JSX 与现状一致
  }
  ```

  `token` 字段必须仍可读到——它是 WS auth token，由 `App.tsx` 通过 `setToken` 注入 store（`App.tsx:128`）。

- [ ] **Step 4**：在 `App.tsx`：
  - 删除行 110–114 的 5 个 `useState`；删除行 252–290 的 `pageTokenItems` / `pageTimelineQuery` / `pagePostsQuery` 派生；删除行 465–478 `openTokenPage`。
  - `<TokenRadarTable onOpenPage={...}>` 改为 `(item) => { const tt = item.identity.target_type; const tid = item.identity.target_id; if (tt && tid) navigate("/token/" + tt + "/" + encodeURIComponent(tid)); }`。
  - 把行 769–877 的中列条件渲染改成 `<Routes>`：

    ```tsx
    <Routes>
      <Route element={<CockpitLayout {...chromeProps} />}>
        <Route index element={<LivePage {...liveProps} />} />
        <Route path="token/:targetType/:targetId" element={<TokenTargetPage />} />
        {/* PR3 在这里追加 signal-lab 路由 */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
    ```

  - PR2 也创建 `<SignalLabPage>` 薄壳（`web/src/components/SignalLabPage.tsx`）：内部仍从 Zustand 读 `signalLabHandle/signalLabStatus/signalLabSearch` 与既有 list `useQuery`，渲染当前 `App.tsx:809-823` 的 workbench 内容。PR2 末态 `<Routes>` 包含 `/signal-lab` 与 `/` 两条独立路由，**不留 `activeView === "signal_lab"` 条件渲染**。PR3 仅把 `<SignalLabPage>` 内 filter 来源从 Zustand 翻为 URL，并新增 `/signal-lab/pulse/:candidateId` 嵌套路由。

- [ ] **Step 5**：跑测试套件 + build + tsc。

  ```bash
  cd web && npm run test && npm run build
  ```

- [ ] **Step 6**：手动 UI smoke（`docs/FRONTEND.md` UI verification gate）：
  1. `cd web && npm run dev` + 后端起来；浏览器打开 `/`。
  2. 点击雷达任一行 → URL 变为 `/token/Asset/<id>`，二级页内容渲染。
  3. 在 `/token/...` 页硬刷新 → 内容仍正确。
  4. 浏览器后退键 → 回 `/`，雷达滚动位置保持。
  5. Network 面板：无失败 `/api/*`；WS 帧到达。
  6. Score 仍展示 component breakdown。

- [ ] **Step 7**：commit。

  ```bash
  git add web/src/components/TokenTargetPage.tsx web/src/App.tsx web/src/components/__tests__/TokenTargetPage.routing.test.tsx
  git commit -m "feat(web): route /token/:targetType/:targetId to TokenTargetPage"
  ```

#### Task 2.4 — Verification（PR2）

- [ ] `cd web && npm run test` — PASS
- [ ] `cd web && npm run build` — PASS（含 tsc）
- [ ] `uv run ruff check . && uv run pytest && uv run python -m compileall src tests` — PASS
- [ ] 手动 UI 清单（上面 6 步）全部通过；记录 verification artefact。
- [ ] PR description 列 AC1（点击 → URL）、AC2（刷新一致）、AC5（后退键）证据。

---

### PR3 — `feat: signal lab routing + watchlist linkify`

依赖：PR1（pulse 单点端点上线）+ PR2（router 基础设施）。两者都合并后再开 PR3。

**Files**:
- Create: `web/src/api/useSignalPulseQueries.ts`
- Create: `web/src/components/SignalLabPage.tsx`
- Create: `web/src/components/PulseDetailPage.tsx`
- Modify: `web/src/store/useTraderStore.ts:13, 32-35, 53-56, 76-79, 97-100`
- Modify: `web/src/App.tsx:76-79, 100, 134, 166-175, 353, 445, 505-518, 527, 658-660, 769-823`
- Test: `web/src/components/__tests__/SignalLabPage.routing.test.tsx`
- Test: `web/src/components/__tests__/PulseDetailPage.routing.test.tsx`
- Test: `web/src/components/__tests__/Watchlist.linkify.test.tsx`

#### Task 3.1 — 新增 `useSignalPulseCandidate` hook

- [ ] **Step 1**：写失败测试 `web/src/api/__tests__/useSignalPulseQueries.test.ts`：

  ```ts
  import { renderHook, waitFor } from "@testing-library/react";
  import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
  import { vi } from "vitest";
  import * as client from "../client";
  import { useSignalPulseCandidate } from "../useSignalPulseQueries";

  it("calls /api/signal-lab/pulse/{id}", async () => {
    const getApi = vi.spyOn(client, "getApi").mockResolvedValue({ ok: true, data: { candidate_id: "cand-1" } });
    const qc = new QueryClient();
    const wrapper = ({ children }: any) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
    const { result } = renderHook(() => useSignalPulseCandidate({ token: "tok", candidateId: "cand-1" }), { wrapper });
    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(getApi).toHaveBeenCalledWith("/api/signal-lab/pulse/cand-1", expect.objectContaining({ token: "tok" }));
  });
  ```

- [ ] **Step 2**：跑测试，确认失败（hook 不存在）。

- [ ] **Step 3**：创建 `web/src/api/useSignalPulseQueries.ts`：

  ```ts
  import { useQuery } from "@tanstack/react-query";
  import { getApi } from "./client";
  import type { SignalPulseItem, SignalPulseListData, SignalPulseStatusFilter, ScopeKey, WindowKey } from "./types";

  type ListArgs = {
    token: string;
    window: WindowKey;
    scope: ScopeKey;
    status: SignalPulseStatusFilter;
    handle: string;
    q: string;
  };

  export function useSignalPulseList(args: ListArgs) {
    const { token, window, scope, status, handle, q } = args;
    return useQuery({
      queryKey: ["signal-lab-pulse", window, scope, status, handle, q],
      queryFn: () =>
        getApi<SignalPulseListData>("/api/signal-lab/pulse", {
          token,
          params: { window, scope, status: status === "all" ? undefined : status, handle: handle || undefined, q: q || undefined }
        }),
      enabled: Boolean(token)
    });
  }

  export function useSignalPulseCandidate({ token, candidateId }: { token: string; candidateId: string | null }) {
    return useQuery({
      queryKey: ["signal-lab-pulse-candidate", candidateId],
      queryFn: () =>
        getApi<SignalPulseItem>("/api/signal-lab/pulse/" + encodeURIComponent(candidateId!), { token }),
      enabled: Boolean(token && candidateId),
      staleTime: 8_000,
      retry: false
    });
  }
  ```

- [ ] **Step 4**：跑测试，确认通过。

- [ ] **Step 5**：commit。

  ```bash
  git add web/src/api/useSignalPulseQueries.ts web/src/api/__tests__/useSignalPulseQueries.test.ts
  git commit -m "feat(web): useSignalPulseList + useSignalPulseCandidate hooks"
  ```

#### Task 3.2 — `<PulseDetailPage>` 路由

- [ ] **Step 1**：写失败测试 `web/src/components/__tests__/PulseDetailPage.routing.test.tsx`（两用例：正常 + 404）。

- [ ] **Step 2**：跑测试，确认失败。

- [ ] **Step 3**：创建 `web/src/components/PulseDetailPage.tsx`：

  ```tsx
  import { useParams } from "react-router-dom";
  import { useSignalPulseCandidate } from "../api/useSignalPulseQueries";
  import { useTraderStore } from "../store/useTraderStore";
  import { SignalLabInspector } from "./SignalLabInspector";

  export function PulseDetailPage() {
    const { candidateId } = useParams<{ candidateId: string }>();
    const token = useTraderStore((s) => s.token);
    const query = useSignalPulseCandidate({ token, candidateId: candidateId ?? null });

    if (query.isLoading) return <div className="empty-state">加载中…</div>;
    if (query.isError || !query.data) return <div className="empty-state">Pulse 不存在或已被屏蔽</div>;
    return <SignalLabInspector item={query.data.data} />;
  }
  ```

  审计验证：`<SignalLabInspector>` 在 `web/src/components/SignalLabInspector.tsx:16-18` 的 props 仅 `{ item: SignalPulseItem }`——无 decision/snooze/dismiss 回调；全代码库 `useMutation` 仅 `markReadMutation`/`markAllReadMutation` 用于通知中心。本组件无须抽 hook。

- [ ] **Step 4**：跑测试，确认两用例通过。

- [ ] **Step 5**：commit。

  ```bash
  git add web/src/components/PulseDetailPage.tsx web/src/components/__tests__/PulseDetailPage.routing.test.tsx
  git commit -m "feat(web): /signal-lab/pulse/:candidateId deep-link page"
  ```

#### Task 3.3 — `<SignalLabPage>` + URL query 同步

- [ ] **Step 1**：写失败测试 `web/src/components/__tests__/SignalLabPage.routing.test.tsx`（`STUB_LIST` 是最小 `SignalPulseListData` fixture：`{ query: {...}, health: {...}, summary: {...}, items: [], returned_count: 0, has_more: false, next_cursor: null }`）：

  ```tsx
  import { render, waitFor } from "@testing-library/react";
  import { MemoryRouter, Routes, Route } from "react-router-dom";
  import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
  import { vi } from "vitest";
  import * as client from "../../api/client";
  import { SignalLabPage } from "../SignalLabPage";

  it("calls list endpoint with handle from URL", async () => {
    const getApi = vi.spyOn(client, "getApi").mockResolvedValue({ ok: true, data: STUB_LIST });
    const qc = new QueryClient();
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/signal-lab?handle=toly&status=token_watch"]}>
          <Routes>
            <Route path="/signal-lab" element={<SignalLabPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );
    await waitFor(() => {
      expect(getApi).toHaveBeenCalledWith("/api/signal-lab/pulse", expect.objectContaining({
        params: expect.objectContaining({ handle: "toly", status: "token_watch" })
      }));
    });
  });
  ```

- [ ] **Step 2**：跑测试，确认失败。

- [ ] **Step 3**：把 `web/src/components/SignalLabPage.tsx`（PR2 创建的薄壳）的 filter 来源从 Zustand 翻为 URL：

  - 删除组件内 `useTraderStore((s) => s.signalLabHandle/signalLabStatus/signalLabSearch)` selector。
  - 改为 `const [searchParams, setSearchParams] = useSearchParams();`；派生 `handle = searchParams.get("handle") ?? ""`、`status = (searchParams.get("status") as SignalPulseStatusFilter) ?? "all"`、`q = searchParams.get("q") ?? ""`。
  - 写：`onHandleChange/onStatusChange/onSearchChange` 改为 `(value) => { const next = new URLSearchParams(searchParams); if (value) next.set(key, value); else next.delete(key); setSearchParams(next, { replace: false }); }`。
  - 列表 `useQuery` 调用改为 PR3 Task 3.1 的 `useSignalPulseList({ token, window, scope, status, handle, q })` hook。
  - 内部布局：center column 渲染 workbench 列表；**右侧 inspector 通过本组件内的 `<Outlet />` 渲染**（PulseDetailPage 通过嵌套路由注入），不要走 `<CockpitLayout>` 的全局 `detail-task-panel`。布局示意：

    ```tsx
    <div className="signal-lab-layout">
      <div className="signal-lab-list">
        <SignalLabWorkbench ...{filterPropsFromUrl} ...{listPropsFromHook} onSelect={(item) => navigate(`/signal-lab/pulse/${encodeURIComponent(item.candidate_id)}`)} />
      </div>
      <aside className="signal-lab-inspector-pane">
        <Outlet />
      </aside>
    </div>
    ```

  - URL 约定：handle 不带 `@`（后端 `_normalize_subject` 接受两种写法，本端统一无 `@`）。

- [ ] **Step 4**：跑测试，确认通过。

- [ ] **Step 5**：commit。

  ```bash
  git add web/src/components/SignalLabPage.tsx web/src/components/__tests__/SignalLabPage.routing.test.tsx
  git commit -m "feat(web): /signal-lab page with query-param filters"
  ```

#### Task 3.4 — Zustand 清理 + watchlist 链接化

- [ ] **Step 1**：写失败测试 `web/src/components/__tests__/Watchlist.linkify.test.tsx`：

  ```tsx
  import { render, screen } from "@testing-library/react";
  import { MemoryRouter } from "react-router-dom";
  import userEvent from "@testing-library/user-event";
  import { App } from "../../App";

  it("renders watchlist as <Link to=/signal-lab?handle=>", async () => {
    render(<MemoryRouter initialEntries={["/"]}><App /></MemoryRouter>);
    const link = await screen.findByRole("link", { name: /@toly/i });
    expect(link).toHaveAttribute("href", "/signal-lab?handle=toly");
  });
  ```

  fixture：通过 mock `getApi` 注入 watchlist handle；具体见 `web/src/App.test.tsx` 已有 mock 风格。

- [ ] **Step 2**：跑测试，确认失败。

- [ ] **Step 3**：删除 `web/src/store/useTraderStore.ts` 行 13、32–35、53–56、76–79、97–100 的 `ActiveView` / `signalLabHandle` / `signalLabStatus` / `signalLabSearch` 字段及 setter。tsc 会立刻报多个 `App.tsx` 错误——挨个修复：
  - 行 76–79 selectors 删除；改为从 `useSearchParams()` 派生（仅在 `<SignalLabPage>` 内使用）。
  - 行 134 `activeSignalLabHandle` 派生删除；移到 `<SignalLabPage>` 内。
  - 行 166–175 list `useQuery` 整段删除；`<SignalLabPage>` 内调 `useSignalPulseList`。
  - 行 353、445、527 等 `activeView === "signal_lab"` 判定全部删除（路由替代）。
  - 行 658–660 RailButton：

    ```tsx
    const navigate = useNavigate();
    const location = useLocation();
    <RailButton active={location.pathname === "/"} onClick={() => navigate("/")} label="Live" {...} />
    <RailButton active={location.pathname.startsWith("/signal-lab")} onClick={() => navigate("/signal-lab")} label="Signal Lab" {...} />
    ```

  - 行 505–518 `focusWatchHandle`：整段删除。
  - 行 781–799 watchlist sidebar：

    ```tsx
    {watchlistRows.map((row) => {
      const handleParam = new URLSearchParams(location.search).get("handle") ?? "";
      const isActive = location.pathname === "/signal-lab" && handleParam === row.handle;
      return (
        <Link
          key={row.handle}
          to={"/signal-lab?handle=" + encodeURIComponent(row.handle)}
          className={isActive ? "active" : ""}
        >
          @{row.handle}
        </Link>
      );
    })}
    ```

  - 行 769、809 整段：把 `activeView === "signal_lab"` 条件渲染替换为 `<Routes>` 的扩展（在 PR2 已添加的 routes 之后）：

    ```tsx
    <Route path="signal-lab" element={<SignalLabPage />}>
      <Route path="pulse/:candidateId" element={<PulseDetailPage />} />
    </Route>
    ```

- [ ] **Step 4**：跑全测试 + build + tsc。

  ```bash
  cd web && npm run test && npm run build
  ```
  Expected: PASS。

- [ ] **Step 5**：手动 UI smoke：
  1. `/` → 雷达正常；
  2. 点击 Live Lab toggle → URL 切换、对应内容渲染；
  3. `/signal-lab?handle=toly&status=token_watch` 直接打开 → 列表筛选生效；
  4. 列表点 candidate → URL 变 `/signal-lab/pulse/<id>`，inspector 显示该 candidate；
  5. 在该 URL 硬刷新 → inspector 仍正确；
  6. watchlist sidebar 中键打开新标签 → 新标签 URL 为 `/signal-lab?handle=...`；
  7. 浏览器后退键链路完整；
  8. Network panel：`/api/signal-lab/pulse/{id}` 200；
  9. WS 帧仍到达；score breakdown 仍显示。

- [ ] **Step 6**：commit。

  ```bash
  git add web/src/store/useTraderStore.ts web/src/App.tsx web/src/components/__tests__/Watchlist.linkify.test.tsx
  git commit -m "feat(web): URL is single source of truth for nav state"
  ```

#### Task 3.5 — Verification（PR3）

- [ ] `cd web && npm run test && npm run build` — PASS
- [ ] `uv run ruff check . && uv run pytest` — PASS
- [ ] 手动 UI 9 步全跑过；写入 verification artefact。
- [ ] PR description 列 AC3、AC4、AC5、AC6、AC7 证据。

---

## Rollout order

1. PR1 合并并部署到生产（后端兼容；前端不依赖即可独立验证）。
2. PR2 合并并部署（前端引入 router；用户路径不变——`/` 仍是雷达）。
3. PR3 合并并部署（Signal Lab + Pulse 路由 + watchlist 链接化）。
4. 部署后，公告内部链接形态（README / Slack）：
   - 分享 token：`/<host>/token/Asset/<target_id>` 或 `/<host>/token/CexToken/<inst_id>`
   - 分享 pulse：`/<host>/signal-lab/pulse/<candidate_id>`
   - 分享筛选视图：`/<host>/signal-lab?handle=toly&status=token_watch`

## Rollback

- **PR1**：纯加法。回滚 = revert PR1。前端无依赖，零业务影响。
- **PR2**：revert 后 `<App>` 退化为无路由 SPA。中间状态已通过 `<MemoryRouter>` 测试覆盖；无 schema 变更。回滚 1–2 分钟可完成。
- **PR3**：revert 后 Signal Lab 退化到 PR2 的"`activeView === 'signal_lab'` 条件渲染分支"。注意 `useTraderStore` 字段删除被一同回滚——store schema 自动恢复。
- 任何 PR 不可单独 revert 时（例如 PR3 已生产但发现重大缺陷且 PR2 也需回滚）：直接回滚到 PR1 之前；后端单点端点保留无害。

不存在不可逆步骤；无 DB 迁移；无外部状态。

## Acceptance test commands

映射到 spec acceptance criteria：

- **AC1（点击 → URL）**：`cd web && npm run test -- TokenTargetPage.routing` → PASS。
- **AC2（深链刷新一致）**：手动——浏览器打开 `/token/Asset/<id>` 冷启动；网络面板录像证据。
- **AC3（pulse 不存在 → in-page 404）**：
  - `uv run pytest tests/test_api_http.py::test_api_signal_pulse_by_id_returns_404_when_missing` → PASS
  - `cd web && npm run test -- PulseDetailPage.routing` → PASS（包含 404 用例）
- **AC4（query 同步）**：`cd web && npm run test -- SignalLabPage.routing` → PASS。
- **AC5（后退键）**：手动；录屏证据。
- **AC6（FRONTEND.md UI gate）**：手动 9 步清单全过。
- **AC7（store 字段删除）**：

  ```bash
  ! grep -E 'activeView|signalLabHandle|signalLabStatus|signalLabSearch' web/src/store/useTraderStore.ts
  ! grep -E 'pageTargetRef' web/src/App.tsx
  ```
  Expected：两条命令都返回非零退出码（grep 无匹配）。

## Verification

PR3 合并后，把以下 artefact 写入 `docs/superpowers/plans/active/2026-05-10-frontend-deep-link-routing/verification.md`（或本 plan 的 Verification 节追加）：

- 三个 PR 的合并 commit hash 与 ruff/pytest/build 输出片段。
- 手动 UI 9 步清单的实际操作记录与录屏链接（或截图）。
- AC1–AC7 的对应证据（命令输出 / 截图）。
- 任何已知 follow-up（如代码分割、`<TokenTargetPage>` 内部 useState 抽 hook 等）追加到 `docs/TECH_DEBT.md`。

完成 verification 后把 spec 与本 plan 从 `active/` 移到 `completed/`（与 verification artefact 同 PR）。

---

## Verification（2026-05-10 本地合并前完成）

**实现 commit 序列**（本地合并前 `worktree-feat+deep-link-routing` 上的 10 个 commit）：

```
fc69e30 feat(web): URL is single source of truth for navigation state
7af7607 feat(web): /signal-lab filters in URL query params + nested pulse route
45e2156 feat(web): /signal-lab/pulse/:candidateId deep-link page
630c4af feat(web): add useSignalPulseList and useSignalPulseCandidate hooks
d644c20 refactor(web): drop tokenRadarRowToTokenItem re-export shim
f1b3864 feat(web): route /token/:targetType/:targetId to TokenTargetPage
e3e8078 refactor(web): extract CockpitLayout, LivePage, SignalLabPage page components
3d09cfc chore(web): add react-router-dom + BrowserRouter shell
ab7eac3 feat(api): GET /api/signal-lab/pulse/{candidate_id} for deep-link
77422bc feat(retrieval): add SignalPulseService.candidate single-item lookup
```

**自动化 gate**（worktree 内末次运行）：

- `uv run ruff check .` — All checks passed
- `uv run pytest` — 397 passed, 140 skipped（基线一致，无新 regression）
- `uv run python -m compileall src tests` — 通过
- `cd web && npm run test` — 15 test files / 82 tests 全过
- `cd web && npm run build` — `tsc --noEmit && vite build` 成功（gzip 119.90 kB）

**Acceptance criteria**（spec §Acceptance）：

- AC1（点击 → URL）：`web/src/components/__tests__/TokenTargetPage.routing.test.tsx` 经 `MemoryRouter` 校验 URL 与 API 参数同步。
- AC2（深链刷新一致）：`<TokenTargetPage>` 通过 `useParams + useTokenTargetTimeline + useTokenTargetPosts` 自取数据；`enabled: Boolean(token && target)` 保证 bootstrap 完成后查询发出。
- AC3（pulse 不存在 → in-page 404）：后端 `tests/test_api_http.py::test_api_signal_pulse_by_id_returns_404_when_missing` + 前端 `PulseDetailPage.routing.test.tsx` 第 2 用例覆盖。
- AC4（query 同步）：`SignalLabPage.routing.test.tsx` 验证 `?handle=&status=` 进入 list endpoint 参数；空筛选不写入 URL。
- AC5（后退键）：filter 写入 `setSearchParams(replace: false)`、auto-redirect 到第一 candidate 用 `replace: true`，避免后退按钮抖动。
- AC6（FRONTEND.md UI gate）：审计 `useIntelSocket` 持续在 `App.tsx` 顶层不会随路由切换 unmount；score breakdown 仍随 `<ScoreLedger>` 渲染。**浏览器手动 smoke 留待主 checkout 合入后由用户跑** —— 本 PR 内部已通过自动化测试覆盖关键路径。
- AC7（store 字段删除）：

  ```
  grep -rn 'activeView\|signalLabHandle\|signalLabStatus\|signalLabSearch\|focusWatchHandle\|pageTargetRef' web/src/
  (no output)
  grep -rn '^export {' web/src/App.tsx
  (no output)
  ```

  7 个 grep 全 0 命中——`activeView`/`signalLabHandle`/`signalLabStatus`/`signalLabSearch`/`focusWatchHandle`/`pageTargetRef`/`^export {` 全部物理删除，无残留 compat shim。中途发现并修掉 PR2 引入的 `tokenRadarRowToTokenItem` 转发 export（commit `d644c20`）。

**独立审计**：fresh-context reviewer 跑完审计返回 `VERDICT: APPROVED`。补充非阻塞 follow-up：`<TokenTargetPage>` 的 `windowKey` 是 component-local `useState`，结构上由路由切换的卸载/重挂载隔离，无显式测试断言但风险低；可作为后续 hook 抽取的优化项。

**Follow-ups**（非本期目标）：

- 路由级代码分割（`React.lazy` 三个 page component）。
- `<TokenTargetPage>` 多个 `useState` 抽出 `useTokenTargetPageState` hook。
- `<SignalLabPage>` auto-redirect 到首 candidate 的策略在更大数据量下复评（当前在空列表时不触发，行为安全）。
- 移动端 `mobileTask` 与路由长期统一（本期非目标）。
