# Tests 与 Lint 生产级化 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `tests/` 扁平 95 文件按 `unit/integration/e2e/architecture/contract/golden` 六层重排；ruff 规则集扩 + ruff-format + mypy strict 渐进 + ESLint flat + Prettier；引入 testcontainers + uvicorn subprocess 跨进程 e2e 黄金路径；PG 不可达由 silent skip 改为 fail-loud + 自动 testcontainers；line ≥ 80% / branch ≥ 70% 覆盖率门槛；完成判定唯一证据来源收紧到 `make check-all`。

**Architecture:** 三道闸（lint+type / unit+arch+contract / integration+e2e+coverage）由 Makefile `&&` 串联强制执行；`make check` 是日常快路径，`make check-all` 是唯一可写入 verification artefact 的证据来源。架构测试范式（AST/grep）从 `tests/` 根迁移到 `tests/architecture/` 不改逻辑，新增 `tests/contract/test_openapi_drift.py` 与 `tests/e2e/test_golden_path.py`。mypy strict 仅在 `domains/`、`platform/`、`cli.py` 白名单内强制；其余包通过 override 推迟，所有 override 写入 TECH_DEBT 跟踪。

**Tech Stack:** Python 3.13, pytest, ruff, mypy, testcontainers-python, uvicorn, httpx, websockets, coverage.py, pre-commit, React/TypeScript, Vitest, ESLint flat config, Prettier, openapi-typescript.

---

**Status**: Draft
**Date**: 2026-05-10
**Owning spec**: `docs/superpowers/specs/active/2026-05-10-tests-and-lint-production-grade-design-cn.md`
**Worktree**: `.worktrees/tests-and-lint-production-grade/`
**Branch**: `harness/tests-and-lint-production-grade`

---

## Pre-flight

执行任何 phase 前必须满足：

- [ ] **Step P-1: 创建 worktree（在仓库根目录）**

```bash
git worktree add .worktrees/tests-and-lint-production-grade -b harness/tests-and-lint-production-grade main
```

- [ ] **Step P-2: 进入 worktree 并验证位置**

```bash
cd .worktrees/tests-and-lint-production-grade
git worktree list
git status --short
git branch --show-current
```

Expected output of `git branch --show-current`: `harness/tests-and-lint-production-grade`

- [ ] **Step P-3: 录基线**

```bash
uv sync
uv run ruff check .
uv run pytest --collect-only -q 2>&1 | tail -3
uv run pytest -q
uv run python -m compileall src tests
cd web && npm install && npm run typecheck && npm test -- --run && cd ..
```

Expected:
- `ruff check .`: 退出 0
- `pytest --collect-only -q`: `563 tests collected`
- `pytest -q`: 全 pass 或仅 PG 不可达的 skip（如 `402 passed, 161 skipped`），无 failed
- `compileall`: 退出 0
- `npm run typecheck` + `npm test`: 退出 0

- [ ] **Step P-4: 记录 baseline 数字到 verification artefact 占位**

创建文件 `docs/superpowers/plans/active/2026-05-10-tests-and-lint-production-grade-verification.md`，先粘贴当前基线数字（test 总数、pass/skip 数、ruff 状态、前端状态），后续每 phase 完成时追加证据。

Known baseline expectation: 无 known-failing test；如基线已有 fail，先修复或显式列出再进 P0。

- [ ] **Step P-5: 不允许跨 worktree 编辑**

确认 `.worktrees/` 下其他 worktree（如 `token-identity-freshness-hard-cut/`、`token-radar-factor-snapshot-hard-cut/`）属于其他任务，本 plan 严禁触碰。

---

## File Structure（plan 范围内会创建/修改的文件全清单）

### 新建文件

**测试基础设施：**
- `tests/conftest.py`（根 conftest，注册 markers + 共享 fixtures）
- `tests/unit/__init__.py`、`tests/unit/conftest.py`
- `tests/integration/__init__.py`、`tests/integration/conftest.py`
- `tests/e2e/__init__.py`、`tests/e2e/conftest.py`、`tests/e2e/_uvicorn_entry.py`、`tests/e2e/_writer_entry.py`、`tests/e2e/test_golden_path.py`
- `tests/architecture/__init__.py`、`tests/architecture/conftest.py`、`tests/architecture/test_completion_gates.py`
- `tests/contract/__init__.py`、`tests/contract/conftest.py`、`tests/contract/test_openapi_drift.py`

**脚本：**
- `scripts/migrate_tests_layout.py`（一次性 git mv 工具）
- `scripts/regen_openapi.py`（FastAPI app.openapi() → docs/generated/openapi.json）

**配置：**
- `.pre-commit-config.yaml`
- `web/eslint.config.js`（flat config）
- `web/.prettierrc.json`
- `web/.prettierignore`

**文档生成产物（入仓）：**
- `docs/generated/openapi.json`
- `web/src/api/types.ts`

### 修改文件

- `pyproject.toml`：扩 `[tool.ruff.lint]` 规则集；新增 `[tool.ruff.format]`；新增 `[tool.ruff.lint.per-file-ignores]`；新增 `[tool.mypy]` + `[[tool.mypy.overrides]]`；新增 `[tool.coverage.run]` + `[tool.coverage.report]`；新增 `[tool.pytest.ini_options]` markers + addopts + `--strict-markers` + `--strict-config`；dev deps 添加 `mypy`、`pytest-cov`、`testcontainers[postgres]`、`websockets`、`pre-commit`
- `Makefile`：新增 `check`、`check-all`、`test-unit`、`test-integration`、`test-e2e`、`test-architecture`、`test-contract`、`coverage`、`contract-check`、`regen-contract`、`install-hooks`；旧 `check`/`test`/`lint`/`compile` 保留为 alias 不变
- `web/package.json`：新增 scripts `lint`、`format:check`、`format`、`generate:types`；devDependencies 加 `eslint@^9`、`@typescript-eslint/parser`、`@typescript-eslint/eslint-plugin`、`eslint-plugin-react`、`eslint-plugin-react-hooks`、`eslint-plugin-import`、`eslint-plugin-jsx-a11y`、`prettier@^3`、`openapi-typescript@^7`
- `docs/TESTING.md`：把"运行 ruff/pytest/compileall"改为引用 `make check-all`，引用新模板
- `docs/WORKFLOW.md`：`Completion gates` 章节同步
- `docs/superpowers/_templates/verification-template.md`：新增三段强制 `Coverage` / `Skipped tests` / `E2E golden path`
- `docs/TECH_DEBT.md`：写入 mypy override 名单与每条 follow-up
- `tests/postgres_test_utils.py`：增加一个 `ensure_postgres_or_fail()` 辅助函数，整段 skip 行为保留兼容；e2e 使用新行为
- 现有 95 个 `tests/test_*.py`：仅 git mv 路径，**不改文件内容**（除非 import path 适配，详见 P1）

### 不动文件

- `src/` 全部业务代码，除非 P3 mypy strict 暴露真实 bug（一事一议，最小修改）
- `tests/factories.py`、`tests/factories_token_radar.py`、`tests/postgres_test_utils.py` 的现有函数签名
- `tests/golden/test_token_radar_corpus.py` 内容
- 现有 alembic 迁移
- compose.yaml

---

## Phase 0 — 测试基础设施脚手架

**Goal:** 在 `tests/` 下创建 6 个空子目录与各自 conftest；根 conftest 注册 markers；`pyproject.toml` 注册 markers + `--strict-markers` + `--strict-config`；Makefile 加 `check`、`check-all` 等占位 target。**完成时旧扁平 tests/ 还在原位**，新目录是空的。pytest 应仍正常 collect 563 用例。

### Task 0.1 — 创建空目录与 `__init__.py`

**Files:**
- Create: `tests/unit/__init__.py`、`tests/integration/__init__.py`、`tests/e2e/__init__.py`、`tests/architecture/__init__.py`、`tests/contract/__init__.py`

- [ ] **Step 0.1.1: 在 worktree 根创建 6 个空目录与 `__init__.py`**

```bash
mkdir -p tests/unit tests/integration tests/e2e tests/architecture tests/contract
touch tests/unit/__init__.py tests/integration/__init__.py tests/e2e/__init__.py tests/architecture/__init__.py tests/contract/__init__.py
```

- [ ] **Step 0.1.2: 验证 pytest collection 仍是 563**

```bash
uv run pytest --collect-only -q 2>&1 | tail -3
```

Expected: `563 tests collected`（新空目录无文件，应不影响 count）

### Task 0.2 — 写根 `tests/conftest.py`

**Files:**
- Create: `tests/conftest.py`

- [ ] **Step 0.2.1: 写根 conftest，集中注册 marker 与共享 fixture（当前仅注册）**

```python
# tests/conftest.py
"""Root conftest: marker registration and cross-layer fixtures."""

from __future__ import annotations

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Markers are registered in pyproject.toml; this is a safety net for IDE collection."""
    # Markers are also declared in pyproject.toml [tool.pytest.ini_options].
    # Listing them here makes them discoverable when pytest is invoked without
    # the project's pyproject.toml on the active config path (e.g. some IDE plugins).
    for marker in ("unit", "integration", "e2e", "architecture", "contract"):
        config.addinivalue_line("markers", f"{marker}: tests in tests/{marker}/")
```

- [ ] **Step 0.2.2: 验证 collection 仍 563、无 marker warning**

```bash
uv run pytest --collect-only -q 2>&1 | tail -5
```

Expected: `563 tests collected`，无 `PytestUnknownMarkWarning`。

### Task 0.3 — 写每个子目录的 conftest（自动 marker）

**Files:**
- Create: `tests/unit/conftest.py`、`tests/integration/conftest.py`、`tests/e2e/conftest.py`（仅占位）、`tests/architecture/conftest.py`、`tests/contract/conftest.py`

- [ ] **Step 0.3.1: `tests/unit/conftest.py` 自动给本目录所有 item 打 unit marker**

```python
# tests/unit/conftest.py
"""Auto-mark every test under tests/unit/ as @pytest.mark.unit."""

from __future__ import annotations

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for item in items:
        if "tests/unit/" in str(item.fspath):
            item.add_marker(pytest.mark.unit)
```

- [ ] **Step 0.3.2: `tests/integration/conftest.py` 同形（marker = integration）**

```python
# tests/integration/conftest.py
"""Auto-mark every test under tests/integration/ as @pytest.mark.integration."""

from __future__ import annotations

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for item in items:
        if "tests/integration/" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
```

- [ ] **Step 0.3.3: `tests/architecture/conftest.py` 同形（marker = architecture）**

```python
# tests/architecture/conftest.py
"""Auto-mark every test under tests/architecture/ as @pytest.mark.architecture."""

from __future__ import annotations

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for item in items:
        if "tests/architecture/" in str(item.fspath):
            item.add_marker(pytest.mark.architecture)
```

- [ ] **Step 0.3.4: `tests/contract/conftest.py` 同形（marker = contract）**

```python
# tests/contract/conftest.py
"""Auto-mark every test under tests/contract/ as @pytest.mark.contract."""

from __future__ import annotations

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for item in items:
        if "tests/contract/" in str(item.fspath):
            item.add_marker(pytest.mark.contract)
```

- [ ] **Step 0.3.5: `tests/e2e/conftest.py` 仅占位（P5 会大改写）**

```python
# tests/e2e/conftest.py
"""Auto-mark every test under tests/e2e/ as @pytest.mark.e2e.

Real fixtures (testcontainers PG, uvicorn subprocess) are added in Phase 5.
"""

from __future__ import annotations

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for item in items:
        if "tests/e2e/" in str(item.fspath):
            item.add_marker(pytest.mark.e2e)
```

- [ ] **Step 0.3.6: 验证 collection 仍 563、所有 conftest 文件被加载**

```bash
uv run pytest --collect-only -q 2>&1 | tail -3
```

Expected: `563 tests collected`，无 import error。

### Task 0.4 — `pyproject.toml` 注册 markers + 严格化

**Files:**
- Modify: `pyproject.toml`（替换 `[tool.pytest.ini_options]` 块）

- [ ] **Step 0.4.1: 把 `pyproject.toml:42-43` 这两行替换为完整配置**

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra --strict-markers --strict-config"
markers = [
  "unit: pure logic, no external dependencies (lives in tests/unit/)",
  "integration: requires real Postgres (lives in tests/integration/)",
  "e2e: cross-process; needs testcontainers + uvicorn subprocess (lives in tests/e2e/)",
  "architecture: AST/grep enforcement of repo invariants (lives in tests/architecture/)",
  "contract: front-back schema/contract drift checks (lives in tests/contract/)",
]
```

- [ ] **Step 0.4.2: 重新 collect，验证无未知 marker warning（当前 0 文件用 marker，应安全）**

```bash
uv run pytest --collect-only -q 2>&1 | tail -5
```

Expected: `563 tests collected`，无 `PytestUnknownMarkWarning`。

### Task 0.5 — Makefile 新 target 占位

**Files:**
- Modify: `Makefile`（在 `.PHONY` 行追加新 target，保留所有旧 target 不变）

- [ ] **Step 0.5.1: 修改 `Makefile` 第一行 `.PHONY` 与 `help`，并在 `compile` 与 `init` 之间插入下列新 target 块**

把 `.PHONY: help sync install ...` 那一行末尾追加：
```
test-unit test-integration test-e2e test-architecture test-contract check-all coverage contract-check regen-contract install-hooks
```

在 `compile:` target 之后、`init:` 之前插入：

```makefile
test-unit: ## run only tests/unit/
	@uv run python -m pytest tests/unit -m unit

test-integration: ## run only tests/integration/ (real Postgres required; auto testcontainers in P5)
	@uv run python -m pytest tests/integration -m integration

test-e2e: ## run only tests/e2e/ (testcontainers + uvicorn subprocess; populated in P5)
	@uv run python -m pytest tests/e2e -m e2e

test-architecture: ## run only tests/architecture/ (AST/grep checks)
	@uv run python -m pytest tests/architecture -m architecture

test-contract: ## run only tests/contract/ (OpenAPI drift; populated in P4)
	@uv run python -m pytest tests/contract -m contract

check-all: ## the only command that may produce verification-artefact evidence (gates 1+2+3)
	@$(MAKE) check
	@$(MAKE) test-integration
	@$(MAKE) test-e2e
	@$(MAKE) coverage

coverage: ## run coverage report (real config in P6)
	@echo "[P6] coverage gate not yet wired; place-holder"

contract-check: ## verify OpenAPI types are in sync (real impl in P4)
	@echo "[P4] contract-check not yet wired; place-holder"

regen-contract: ## regenerate openapi.json + web/src/api/types.ts (real impl in P4)
	@echo "[P4] regen-contract not yet wired; place-holder"

install-hooks: ## install pre-commit hooks (real impl in P2)
	@echo "[P2] install-hooks not yet wired; place-holder"
```

- [ ] **Step 0.5.2: 验证旧入口与新占位都能跑**

```bash
make help | head -30
make test-unit  # should collect 0 (no files yet) and exit 0
make check       # legacy alias (test+lint+compile) still works
```

Expected: `make test-unit` 退出 0 输出 `no tests ran in ...`（因为 unit/ 目录里还没有 test）。`make check` 跑出原 `test+lint+compile` 完整结果。

### Task 0.6 — Phase 0 commit

- [ ] **Step 0.6.1: 提交 P0 全部改动**

```bash
git add tests/ pyproject.toml Makefile
git status --short
git commit -m "$(cat <<'EOF'
test: scaffold layered test directories (P0)

新建空 unit/integration/e2e/architecture/contract conftest 与 __init__；
pyproject.toml 注册 5 个 marker + --strict-markers + --strict-config；
Makefile 加 test-<layer> / check-all / coverage / contract-check 占位 target。
旧扁平 tests/ 与原 make check 保持原位、原行为。

Owning spec: docs/superpowers/specs/active/2026-05-10-tests-and-lint-production-grade-design-cn.md
Phase: 0/6

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

### Phase 0 verification

- [ ] **Step 0.V.1: 全量回归**

```bash
uv run pytest --collect-only -q 2>&1 | tail -3
uv run pytest -q
uv run ruff check .
make help
```

Expected:
- `563 tests collected`
- `pytest -q` pass count 与基线一致
- `ruff check .` 退出 0
- `make help` 列出新 target

把上述输出粘贴到 verification 文件 P0 section。

---

## Phase 1 — 一次性 git mv 大搬家

**Goal:** 把扁平 `tests/test_*.py` 95 个文件按 §6.2 规则全部 git mv 到对应子目录。**不改文件内容**（除非 import path 必须适配）。完成时 `find tests -maxdepth 1 -name 'test_*.py'` 返回空，pytest collection 仍是 563。

### Task 1.1 — 写迁移脚本（dry-run 优先）

**Files:**
- Create: `scripts/migrate_tests_layout.py`

- [ ] **Step 1.1.1: 写迁移脚本骨架**

```python
# scripts/migrate_tests_layout.py
"""One-shot mover: classify tests/test_*.py into layered subdirs.

Classification rules (priority order, first match wins):
  1. tests/golden/* -> stay (already classified)
  2. filename matches *architecture* OR test_harness_structure* OR test_project_structure* -> tests/architecture/
  3. file imports postgres_test_utils -> tests/integration/
  4. filename matches test_compose_* OR test_docs_generated* -> tests/integration/
  5. otherwise -> tests/unit/

Usage:
  python scripts/migrate_tests_layout.py --dry-run    # print plan only
  python scripts/migrate_tests_layout.py --execute    # actually run git mv
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"

ARCH_PATTERNS = (
    re.compile(r"test_.*architecture.*\.py$"),
    re.compile(r"test_harness_structure.*\.py$"),
    re.compile(r"test_project_structure.*\.py$"),
)
PG_INTEGRATION_PATTERNS = (
    re.compile(r"test_compose_.*\.py$"),
    re.compile(r"test_docs_generated.*\.py$"),
)
PG_IMPORT_PATTERNS = (
    re.compile(r"^\s*(from\s+tests\.postgres_test_utils|from\s+\.postgres_test_utils|import\s+tests\.postgres_test_utils|from\s+postgres_test_utils|import\s+postgres_test_utils)", re.MULTILINE),
)


def classify(path: Path) -> str:
    name = path.name
    for pat in ARCH_PATTERNS:
        if pat.match(name):
            return "architecture"
    for pat in PG_INTEGRATION_PATTERNS:
        if pat.match(name):
            return "integration"
    text = path.read_text(encoding="utf-8")
    for pat in PG_IMPORT_PATTERNS:
        if pat.search(text):
            return "integration"
    return "unit"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not (args.dry_run or args.execute):
        parser.error("must specify --dry-run or --execute")

    flat_files = sorted(p for p in TESTS.glob("test_*.py") if p.is_file())
    plan: list[tuple[Path, Path]] = []
    for src in flat_files:
        layer = classify(src)
        dst = TESTS / layer / src.name
        plan.append((src, dst))

    summary: dict[str, int] = {}
    for _, dst in plan:
        layer = dst.parent.name
        summary[layer] = summary.get(layer, 0) + 1

    print(f"# {len(plan)} files to move")
    for src, dst in plan:
        print(f"git mv {src.relative_to(ROOT)} {dst.relative_to(ROOT)}")
    print(f"\n# summary: {summary}")

    if args.execute:
        for src, dst in plan:
            subprocess.run(["git", "mv", str(src), str(dst)], check=True, cwd=ROOT)
        print(f"\n# moved {len(plan)} files")

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 1.1.2: dry-run 看分类结果**

```bash
uv run python scripts/migrate_tests_layout.py --dry-run | tee /tmp/migrate-plan.txt | tail -20
```

Expected: 95 行 `git mv`，summary 大致 `{'unit': ~50-60, 'integration': ~30-40, 'architecture': 2-4}`。

- [ ] **Step 1.1.3: 人工抽查 5 个分类**

```bash
grep -E "test_(api_http|baseline_scoring|src_domain_architecture|compose_postgres|tweet_text)\.py" /tmp/migrate-plan.txt
```

Expected:
- `test_api_http.py` → `tests/integration/`（用 postgres）
- `test_baseline_scoring.py` → `tests/unit/`
- `test_src_domain_architecture.py` → `tests/architecture/`
- `test_compose_postgres.py` → `tests/integration/`
- `test_tweet_text.py` → `tests/unit/`

如有错配，修 `classify()` 并 dry-run 重跑。

### Task 1.2 — 执行 git mv

- [ ] **Step 1.2.1: 实跑迁移**

```bash
uv run python scripts/migrate_tests_layout.py --execute
git status --short | head -20
```

Expected: 95 行 `R  tests/test_X.py -> tests/<layer>/test_X.py`。

- [ ] **Step 1.2.2: 验证 collection 仍是 563**

```bash
uv run pytest --collect-only -q 2>&1 | tail -3
```

Expected: `563 tests collected`，**数字必须完全一致**。如果 != 563，立刻 stop 并诊断（多半是 import 路径或 conftest discovery 问题）。

- [ ] **Step 1.2.3: 验证 markers 自动生效**

```bash
uv run pytest --collect-only -q -m unit 2>&1 | tail -3
uv run pytest --collect-only -q -m integration 2>&1 | tail -3
uv run pytest --collect-only -q -m architecture 2>&1 | tail -3
```

Expected: 三层各自 collected count 之和 + golden（其属 e2e 但目前未 mark） = 563。如果 unit + integration + architecture 不等于 ~562，重审 §6.2 分类规则。

- [ ] **Step 1.2.4: 跑一次完整 pytest 确认无回归**

```bash
uv run pytest -q
```

Expected: pass/skip 数与 baseline 完全一致，无 failed。

### Task 1.2.5 — 修复 5 个被搬迁测试的硬编码路径解析

下列 5 个文件在 git mv 后会因为 `Path(__file__).resolve().parents[1]` 或 `parent.parent` 多了一层目录而错算 ROOT，导致测试断在 collect 阶段。必须在跑 `pytest` 之前修。

**Files:**
- Modify: `tests/architecture/test_src_domain_architecture.py`
- Modify: `tests/architecture/test_harness_structure.py`
- Modify: `tests/architecture/test_project_structure.py`
- Modify: `tests/integration/test_docs_generated.py`
- Modify: `tests/unit/test_gmgn_directory_client.py`

- [ ] **Step 1.2.5.1: 修 `tests/architecture/test_src_domain_architecture.py:6`**

把 `ROOT = Path(__file__).resolve().parents[1]` 改为 `ROOT = Path(__file__).resolve().parents[2]`。

- [ ] **Step 1.2.5.2: 修 `tests/architecture/test_harness_structure.py:10`**

把 `REPO_ROOT = Path(__file__).resolve().parent.parent` 改为 `REPO_ROOT = Path(__file__).resolve().parent.parent.parent`。

- [ ] **Step 1.2.5.3: 修 `tests/architecture/test_project_structure.py:6`**

把 `ROOT = Path(__file__).resolve().parents[1]` 改为 `ROOT = Path(__file__).resolve().parents[2]`。

- [ ] **Step 1.2.5.4: 修 `tests/integration/test_docs_generated.py:11`**

把 `REPO_ROOT = Path(__file__).resolve().parent.parent` 改为 `REPO_ROOT = Path(__file__).resolve().parent.parent.parent`。

- [ ] **Step 1.2.5.5: 修 `tests/unit/test_gmgn_directory_client.py:15`**

把 `FIXTURE_DIR = Path(__file__).parent / "fixtures"` 改为 `FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"`。

- [ ] **Step 1.2.5.6: 重跑 pytest 全集，验证 5 个文件不再因路径错而 fail/error**

```bash
uv run pytest tests/architecture tests/integration/test_docs_generated.py tests/unit/test_gmgn_directory_client.py -v 2>&1 | tail -20
```

Expected: 测试要么 pass，要么因为 `pytest.skip(no postgres)` 等已知原因 skip，不应有 `FileNotFoundError` / `AssertionError: pyproject.toml not found` 等路径相关 error。

- [ ] **Step 1.2.5.7: 防御性 grep 确认 tests/ 下没有其他 `parents[1]` 隐患**

```bash
grep -rn "parents\[1\]\|\.parent\.parent\b" tests/ 2>&1 | grep -v conftest.py | grep -v ".pyc"
```

Expected: 仅返回上面 5 个文件中已修过的行（路径解析中现在是 `parents[2]` 或 `.parent.parent.parent`，正常）。如有其他文件命中且未修，立即修。

### Task 1.3 — 适配 `golden/` marker

`tests/golden/test_token_radar_corpus.py` 在 §6.2 中归类为 e2e 语义（独立目录保留），但目前不在 `tests/e2e/` 下，所以 `tests/e2e/conftest.py` 的 auto-mark 不会对它生效。需要给 golden 目录加自己的 conftest。

**Files:**
- Create: `tests/golden/conftest.py`

- [ ] **Step 1.3.1: 写 `tests/golden/conftest.py` 自动加 e2e marker**

```python
# tests/golden/conftest.py
"""Auto-mark golden corpus tests as @pytest.mark.e2e.

These tests run a real ingest -> projection pipeline against a real Postgres,
so they belong to the e2e gate by semantics even though they live in their
own directory for organizational reasons.
"""

from __future__ import annotations

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for item in items:
        if "tests/golden/" in str(item.fspath):
            item.add_marker(pytest.mark.e2e)
```

- [ ] **Step 1.3.2: 验证 golden 测试现在带 e2e marker**

```bash
uv run pytest --collect-only -q -m e2e 2>&1 | tail -5
```

Expected: 至少 1 个 collected item（来自 `tests/golden/test_token_radar_corpus.py`）。

### Task 1.4 — Phase 1 commit

- [ ] **Step 1.4.1: 单一 commit 包含全部 git mv + 迁移脚本 + golden conftest**

```bash
git add scripts/migrate_tests_layout.py tests/golden/conftest.py
git status --short | head -10
git commit -m "$(cat <<'EOF'
test: layered test layout — git mv 95 files into unit/integration/architecture (P1)

scripts/migrate_tests_layout.py 按机械规则分类：
- tests/test_*architecture* / test_harness_structure* / test_project_structure* -> tests/architecture/
- import postgres_test_utils 或 test_compose_* / test_docs_generated* -> tests/integration/
- 其余 -> tests/unit/
- tests/golden/* 保留原位，conftest 自动加 e2e marker

pytest --collect-only 仍 563 用例；不改任何文件内容。

Owning spec: docs/superpowers/specs/active/2026-05-10-tests-and-lint-production-grade-design-cn.md
Phase: 1/6

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

### Phase 1 verification

- [ ] **Step 1.V.1: 跑全量回归 + 分层验证**

```bash
uv run pytest --collect-only -q 2>&1 | tail -3
uv run pytest -q 2>&1 | tail -3
find tests -maxdepth 1 -name 'test_*.py' | wc -l
ls tests/unit/ tests/integration/ tests/architecture/ | head -20
```

Expected:
- `563 tests collected`
- pytest pass/skip 与基线一致
- `find` 返回 0
- 三个目录各有若干 `test_*.py` 文件

把输出粘贴到 verification 文件 P1 section。

---

## Phase 2 — Lint 矩阵升级（ruff 规则扩 + ESLint flat + Prettier + pre-commit）

**Goal:** ruff 规则集扩到 `E F I UP B SIM S ASYNC RUF PERF PL`；启用 `ruff format`；前端引入 ESLint flat config + Prettier；落地 `.pre-commit-config.yaml`；`make install-hooks` 一键安装。完成时 `make check` 在新规则下退出 0。

### Task 2.1 — 扩 ruff lint 规则集

**Files:**
- Modify: `pyproject.toml`（替换 `[tool.ruff.lint]` 块）

- [ ] **Step 2.1.1: 修改 `pyproject.toml` 中的 ruff 配置**

把 `[tool.ruff]` + `[tool.ruff.lint]` 那一段（`pyproject.toml:45-51`）替换为：

```toml
[tool.ruff]
line-length = 120
target-version = "py313"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM", "S", "ASYNC", "RUF", "PERF", "PL"]
# Common pragmatic ignores. Each ignore is a deliberate choice:
# - PLR0913: too many args is sometimes correct for adapters/factories
# - PLR2004: magic numbers in tests are normal (also blocked by per-file-ignores)
# - PLR0911/PLR0912/PLR0915: cyclomatic complexity caps too low for a few orchestration funcs
# - S101: assert is fine; only flagged in non-test code via per-file-ignores
ignore = [
  "PLR0913",
  "PLR2004",
  "PLR0911",
  "PLR0912",
  "PLR0915",
]

[tool.ruff.lint.per-file-ignores]
"tests/**" = [
  "S101",   # asserts are the test contract
  "S105",   # hard-coded "passwords" in tests are fixtures
  "S106",
  "S311",   # pseudo-random in tests is fine
  "PLR2004",
  "ASYNC",
]
"scripts/**" = [
  "S603",   # subprocess inputs are local CLI args
  "S607",
]

[tool.ruff.format]
# Default settings; line-length inherited from [tool.ruff] = 120
```

- [ ] **Step 2.1.2: 跑新规则集，先记录违规数**

```bash
uv run ruff check . 2>&1 | tail -30
uv run ruff check . --statistics 2>&1 | tail -20
```

预期会有违规（之前的代码没经过新规则审查）。把违规计数表记录下来。

- [ ] **Step 2.1.3: 用 `--fix` 自动修可修的**

```bash
uv run ruff check . --fix
uv run ruff check . --statistics 2>&1 | tail -20
```

剩下的违规需要人工评估：要么修代码、要么加 `# noqa: <code>` 局部抑制（带 reason 注释）、要么进 ignore 名单。

- [ ] **Step 2.1.4: 人工逐项修剩余违规**

对每个剩余 lint 错误：
1. 先看是否真问题（如 `S301: pickle.loads with untrusted input` → 真的话改代码）
2. 否则用 `# noqa: <code> -- <reason>` 局部抑制
3. 仅在全仓有 ≥ 5 处误报且 reason 一致时再加全局 `ignore`

迭代直到：

```bash
uv run ruff check .
# exit 0
```

- [ ] **Step 2.1.5: 跑 ruff format**

```bash
uv run ruff format --check . 2>&1 | tail -10
```

如果有 `Would reformat: ...` 输出，说明文件未按 ruff format 格式化。先查看 diff：

```bash
uv run ruff format --check --diff . 2>&1 | head -50
```

如果 diff 合理（仅风格调整），跑：

```bash
uv run ruff format .
uv run ruff format --check .
# exit 0
```

- [ ] **Step 2.1.6: 跑全量 pytest 确认 ruff 修改未引入回归**

```bash
uv run pytest -q 2>&1 | tail -3
```

Expected: pass/skip 与基线一致。

### Task 2.2 — 前端 ESLint flat config + Prettier

**Files:**
- Create: `web/eslint.config.js`、`web/.prettierrc.json`、`web/.prettierignore`
- Modify: `web/package.json`（scripts + devDependencies）

- [ ] **Step 2.2.1: 安装 dev 依赖**

```bash
cd web && npm install --save-dev \
  eslint@^9 \
  @typescript-eslint/parser@^8 \
  @typescript-eslint/eslint-plugin@^8 \
  eslint-plugin-react@^7 \
  eslint-plugin-react-hooks@^5 \
  eslint-plugin-import@^2 \
  eslint-plugin-jsx-a11y@^6 \
  prettier@^3 \
  globals@^15
cd ..
```

- [ ] **Step 2.2.2: 写 `web/eslint.config.js`（flat config）**

```javascript
// web/eslint.config.js
// Flat config — ESLint 9+
import tsParser from "@typescript-eslint/parser";
import tsPlugin from "@typescript-eslint/eslint-plugin";
import reactPlugin from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";
import importPlugin from "eslint-plugin-import";
import jsxA11y from "eslint-plugin-jsx-a11y";
import globals from "globals";

export default [
  {
    ignores: ["dist/**", "node_modules/**", "src/api/types.ts"],
  },
  {
    files: ["src/**/*.{ts,tsx}"],
    languageOptions: {
      parser: tsParser,
      parserOptions: {
        ecmaVersion: 2022,
        sourceType: "module",
        ecmaFeatures: { jsx: true },
      },
      globals: {
        ...globals.browser,
        ...globals.es2022,
      },
    },
    plugins: {
      "@typescript-eslint": tsPlugin,
      react: reactPlugin,
      "react-hooks": reactHooks,
      import: importPlugin,
      "jsx-a11y": jsxA11y,
    },
    rules: {
      // Base
      "no-console": ["warn", { allow: ["warn", "error"] }],
      "no-unused-vars": "off",
      // TypeScript
      "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_" }],
      "@typescript-eslint/no-explicit-any": "warn",
      "@typescript-eslint/consistent-type-imports": "error",
      // React
      "react/jsx-uses-react": "off",
      "react/react-in-jsx-scope": "off",
      "react/jsx-key": "error",
      // React hooks
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",
      // Import
      "import/no-duplicates": "error",
      "import/order": ["warn", {
        groups: ["builtin", "external", "internal", "parent", "sibling", "index"],
        "newlines-between": "always",
        alphabetize: { order: "asc" },
      }],
      // a11y
      "jsx-a11y/alt-text": "warn",
    },
    settings: {
      react: { version: "detect" },
    },
  },
  {
    files: ["src/**/*.test.{ts,tsx}", "src/test/**/*.{ts,tsx}"],
    rules: {
      "@typescript-eslint/no-explicit-any": "off",
      "no-console": "off",
    },
  },
];
```

- [ ] **Step 2.2.3: 写 `web/.prettierrc.json`**

```json
{
  "printWidth": 100,
  "singleQuote": false,
  "trailingComma": "all",
  "arrowParens": "always",
  "semi": true,
  "tabWidth": 2
}
```

- [ ] **Step 2.2.4: 写 `web/.prettierignore`**

```
dist/
node_modules/
src/api/types.ts
package-lock.json
```

- [ ] **Step 2.2.5: 在 `web/package.json` scripts 加 lint/format**

把 `"scripts": { ... }` 改为：

```json
{
  "scripts": {
    "dev": "vite --host 127.0.0.1 --port 5173",
    "build": "tsc --noEmit && vite build",
    "preview": "vite preview --host 127.0.0.1 --port 4173",
    "test": "vitest run",
    "typecheck": "tsc --noEmit",
    "lint": "eslint --max-warnings=0 src",
    "format:check": "prettier --check 'src/**/*.{ts,tsx,css,json}'",
    "format": "prettier --write 'src/**/*.{ts,tsx,css,json}'",
    "generate:types": "openapi-typescript ../docs/generated/openapi.json -o src/api/types.ts"
  }
}
```

`generate:types` 在 P4 会用到；先放 scripts，但实际依赖 `openapi-typescript` 在 P4 安装。

- [ ] **Step 2.2.6: 跑 lint，记录违规数**

```bash
cd web && npm run lint 2>&1 | tail -30; cd ..
```

预期会有 warning/error。逐项处理（同 ruff 的处理思路）。

- [ ] **Step 2.2.7: 跑 prettier --write，再跑 --check**

```bash
cd web && npx prettier --write 'src/**/*.{ts,tsx,css,json}' && npm run format:check; cd ..
```

Expected: `format:check` 退出 0。

- [ ] **Step 2.2.8: 再跑 lint 直到 0 warning + 0 error**

```bash
cd web && npm run lint 2>&1 | tail -10; cd ..
```

Expected: 退出 0，无 warning（`--max-warnings=0`）。

- [ ] **Step 2.2.9: 验证 vitest 与 typecheck 仍通过**

```bash
cd web && npm run typecheck && npm test -- --run; cd ..
```

Expected: 全 pass。

### Task 2.3 — Pre-commit 配置

**Files:**
- Create: `.pre-commit-config.yaml`

- [ ] **Step 2.3.1: 写 `.pre-commit-config.yaml`**

```yaml
# .pre-commit-config.yaml
# Hooks run on every commit. They are gate-1 only — the canonical "is-it-green" entry
# point is `make check-all`, which is what verification artefacts must paste.
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.8.6
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: local
    hooks:
      - id: mypy-domain-platform-cli
        name: mypy (domains/, platform/, cli.py — strict)
        entry: uv run mypy
        language: system
        types: [python]
        files: ^src/parallax/(domains|platform)/.*\.py$|^src/parallax/cli\.py$
        pass_filenames: false
        args: ["src/parallax"]

      - id: eslint-web
        name: eslint (web/src)
        entry: bash -c 'cd web && npm run lint'
        language: system
        types_or: [ts, tsx]
        files: ^web/src/.*\.(ts|tsx)$
        pass_filenames: false

      - id: prettier-web
        name: prettier (web/src)
        entry: bash -c 'cd web && npm run format:check'
        language: system
        types_or: [ts, tsx, css, json]
        files: ^web/.*\.(ts|tsx|css|json)$
        pass_filenames: false
```

注意：mypy 和 eslint hook 在 P3 之前不会真的跑（mypy 还没装、eslint 是 P2 这一步才装），但 hook 配置可以先就位。

- [ ] **Step 2.3.2: `pyproject.toml` dev deps 加 `pre-commit`**

修改 `pyproject.toml [dependency-groups]` 块为：

```toml
[dependency-groups]
dev = [
    "pytest>=8.3.0",
    "ruff>=0.8.6",
    "pre-commit>=3.7",
]
```

- [ ] **Step 2.3.3: 同步依赖**

```bash
uv sync
```

- [ ] **Step 2.3.4: 实现 `make install-hooks`**

把 Makefile 中 `install-hooks` target 的占位行替换为：

```makefile
install-hooks: ## install pre-commit hooks
	@uv run pre-commit install
```

- [ ] **Step 2.3.5: 安装并跑一次 hooks**

```bash
make install-hooks
uv run pre-commit run --all-files 2>&1 | tail -30
```

预期 mypy hook 会失败（P3 还没配置），其他 hook 应通过。如果 mypy hook 阻塞测试，临时把它从 `.pre-commit-config.yaml` 注释掉（用 `# enable in P3` 注释），P3 再开。

- [ ] **Step 2.3.6: 临时注释 mypy hook（P3 再开）**

修改 `.pre-commit-config.yaml`，把 `mypy-domain-platform-cli` hook 整段加 `# TODO P3 enable:` 前缀注释掉。重跑：

```bash
uv run pre-commit run --all-files 2>&1 | tail -15
```

Expected: 全 pass。

### Task 2.4 — 实现 `make check`（gate 1 + gate 2）

**Files:**
- Modify: `Makefile`（替换 `check` target）

- [ ] **Step 2.4.1: 把 Makefile 中的 `check` target 替换为正式实现**

把现有 `check: test lint compile` 这一行替换为：

```makefile
check: ## gates 1+2: lint + type + unit + arch + contract (no external deps; ~10s)
	@uv run ruff check .
	@uv run ruff format --check .
	@cd web && npm run typecheck && npm run lint && npm run format:check && cd ..
	@uv run python -m pytest tests/unit tests/architecture tests/contract -m "unit or architecture or contract"
	@uv run python -m compileall src tests
```

mypy 行先省略（P3 加）。Contract 测试 P4 才有；目前空集合也能 pass。

- [ ] **Step 2.4.2: 跑 `make check`**

```bash
make check 2>&1 | tail -30
```

Expected: 退出 0。

- [ ] **Step 2.4.3: 跑 `time make check`，记录耗时**

```bash
time make check
```

Expected: < 30s（首次可能慢）。把数字记录到 verification artefact P2 section。

### Task 2.5 — Phase 2 commit

- [ ] **Step 2.5.1: 提交 P2 改动**

```bash
git add pyproject.toml Makefile .pre-commit-config.yaml web/eslint.config.js web/.prettierrc.json web/.prettierignore web/package.json web/package-lock.json
# any noqa or # type: ignore added during lint cleanup also goes in
git add src/ tests/ 2>/dev/null || true
git status --short | head -30
git commit -m "$(cat <<'EOF'
chore: lint matrix to production grade — ruff S/ASYNC/RUF/PERF/PL + ruff format + ESLint flat + Prettier + pre-commit (P2)

ruff: 扩规则集 + per-file-ignores 给 tests/scripts 适当放过；启用 ruff format。
前端: ESLint 9 flat config + Prettier 3；@typescript-eslint strict + react-hooks/import/jsx-a11y。
.pre-commit-config.yaml: ruff/ruff-format/eslint/prettier hook（mypy hook P3 启用）。
Makefile: install-hooks 实装；check target 重写为 gate 1 + gate 2（unit/arch/contract）。

Owning spec: docs/superpowers/specs/active/2026-05-10-tests-and-lint-production-grade-design-cn.md
Phase: 2/6

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

### Phase 2 verification

- [ ] **Step 2.V.1: 完整验证**

```bash
make check
uv run pytest -q
cd web && npm test -- --run; cd ..
uv run pre-commit run --all-files 2>&1 | tail -15
```

把输出粘贴到 verification 文件 P2 section。

---

## Phase 3 — mypy strict 渐进

**Goal:** 装 mypy；`pyproject.toml [tool.mypy]` 全局 strict + override 把非白名单包临时放过；逐包修 `domains/`、`platform/`、`cli.py` 真实类型问题；override 名单与每条 follow-up 写入 `docs/TECH_DEBT.md`；启用 pre-commit mypy hook；`make check` 加 mypy。

### Task 3.1 — 安装 mypy 与基础配置

**Files:**
- Modify: `pyproject.toml`（dev deps + `[tool.mypy]` 块）

- [ ] **Step 3.1.1: dev deps 加 mypy**

修改 `pyproject.toml [dependency-groups]`：

```toml
[dependency-groups]
dev = [
    "pytest>=8.3.0",
    "ruff>=0.8.6",
    "pre-commit>=3.7",
    "mypy>=1.13",
]
```

跑 `uv sync`。

- [ ] **Step 3.1.2: `pyproject.toml` 加 mypy 配置**

在文件末尾追加：

```toml
[tool.mypy]
python_version = "3.13"
strict = true
warn_unused_ignores = true
warn_redundant_casts = true
no_implicit_optional = true
namespace_packages = true
explicit_package_bases = true
mypy_path = "src"
plugins = ["pydantic.mypy"]

# Whitelisted packages: must pass strict (do NOT add overrides for these in this spec).
# Everything else is allowed `disallow_untyped_defs = false` until subsequent specs消化.

[[tool.mypy.overrides]]
module = "parallax.app.*"
disallow_untyped_defs = false
disallow_incomplete_defs = false
disallow_untyped_decorators = false

[[tool.mypy.overrides]]
module = "parallax.integrations.*"
disallow_untyped_defs = false
disallow_incomplete_defs = false
disallow_untyped_decorators = false

# Third-party libs without stubs
[[tool.mypy.overrides]]
module = ["alembic.*", "loguru.*", "psycopg.*", "apprise.*", "curl_cffi.*", "websockets.*", "openai_agents.*", "solders.*", "eth_hash.*", "eth_utils.*", "testcontainers.*"]
ignore_missing_imports = true
```

- [ ] **Step 3.1.3: 跑 mypy，记录全仓违规数**

```bash
uv run mypy src 2>&1 | tail -20
uv run mypy src 2>&1 | grep -c "^src/" || echo 0
```

预期非零（白名单包内有真问题）。把数字记录下来。

### Task 3.2 — 修 domains/ 的类型问题

- [ ] **Step 3.2.1: 仅跑 domains 的错误**

```bash
uv run mypy src/parallax/domains 2>&1 | tee /tmp/mypy-domains.txt | tail -30
```

- [ ] **Step 3.2.2: 逐文件修复**

按模块分组处理。每修一组，跑：

```bash
uv run mypy src/parallax/domains 2>&1 | tail -5
```

直到错误数为 0。

修复指引：
- 缺类型注解 → 补
- `Optional` 隐式 → 显式 `T | None`
- pydantic model 类型推断错 → 用 `pydantic.mypy` plugin 已配置，应自动解决；否则补 `Field(...)` 注解
- 跨包类型循环 → 用 `from __future__ import annotations` + `if TYPE_CHECKING`
- 真 bug（罕见）→ 修代码 + 加 regression test 在 `tests/unit/`

不允许的修复：
- 给 `domains/` 加 mypy override（白名单内不允许）
- `# type: ignore` 不带 reason 注释（必须 `# type: ignore[code]  # <why>`）

- [ ] **Step 3.2.3: 验证 domains 全绿**

```bash
uv run mypy src/parallax/domains
# Success: no issues found
```

### Task 3.3 — 修 platform/ 与 cli.py

- [ ] **Step 3.3.1: 跑 platform**

```bash
uv run mypy src/parallax/platform 2>&1 | tail -20
```

- [ ] **Step 3.3.2: 修复同 Task 3.2.2，到 0 error**

- [ ] **Step 3.3.3: 跑 cli.py**

```bash
uv run mypy src/parallax/cli.py 2>&1 | tail -10
```

- [ ] **Step 3.3.4: 修复，到 0 error**

- [ ] **Step 3.3.5: 跑全 src，验证白名单全绿（其他包应被 override 放过）**

```bash
uv run mypy src 2>&1 | tail -15
# Success: no issues found in N source files
```

如有非白名单包仍 error，说明 override 没盖到；调 `pyproject.toml` `[[tool.mypy.overrides]] module` 模块名。

### Task 3.4 — TECH_DEBT 写入 override 清单

**Files:**
- Modify: `docs/TECH_DEBT.md`

- [ ] **Step 3.4.1: 在 `docs/TECH_DEBT.md` 末尾追加 mypy override section**

```markdown
## mypy strict overrides（来自 spec 2026-05-10-tests-and-lint-production-grade）

以下包当前以 `disallow_untyped_defs = false` 等放宽设置通过 mypy。每条都需要后续按包消化（一个 sprint 摘掉一两条）。`no_implicit_optional` 与 `warn_unused_ignores` 等基础项仍全局严格。

| 模块 glob | 放宽项 | follow-up |
|---|---|---|
| `parallax.app.*` | `disallow_untyped_defs/incomplete_defs/untyped_decorators = false` | TODO: 由独立 spec 处理 wiring & runtime 类型注解 |
| `parallax.integrations.*` | 同上 | TODO: external connector 类型注解 |
```

### Task 3.5 — 启用 pre-commit mypy hook

**Files:**
- Modify: `.pre-commit-config.yaml`（解开 P2 注释）

- [ ] **Step 3.5.1: 把 `mypy-domain-platform-cli` hook 解注释**

把 P2 步骤 2.3.6 加的 `# TODO P3 enable:` 注释行全部去掉，恢复完整 hook 块。

- [ ] **Step 3.5.2: 跑一次 hook 验证**

```bash
uv run pre-commit run mypy-domain-platform-cli --all-files 2>&1 | tail -10
```

Expected: pass。

### Task 3.6 — `make check` 加 mypy

**Files:**
- Modify: `Makefile`（在 `check` 中插入 mypy）

- [ ] **Step 3.6.1: 在 `check` target 里 `ruff format --check .` 后插一行**

```makefile
	@uv run mypy src
```

整个 check target 现在是：

```makefile
check: ## gates 1+2: lint + type + unit + arch + contract (no external deps; ~10s)
	@uv run ruff check .
	@uv run ruff format --check .
	@uv run mypy src
	@cd web && npm run typecheck && npm run lint && npm run format:check && cd ..
	@uv run python -m pytest tests/unit tests/architecture tests/contract -m "unit or architecture or contract"
	@uv run python -m compileall src tests
```

- [ ] **Step 3.6.2: 跑 `make check`**

```bash
time make check
```

Expected: 退出 0；耗时 < 60s。

### Task 3.7 — Phase 3 commit

- [ ] **Step 3.7.1: 提交**

```bash
git add pyproject.toml .pre-commit-config.yaml Makefile docs/TECH_DEBT.md src/
git status --short | head -20
git commit -m "$(cat <<'EOF'
chore: mypy strict on domains/platform/cli (P3)

mypy>=1.13 dev dep；[tool.mypy] strict + pydantic.mypy plugin。
overrides: app.* / integrations.* 暂时放宽 disallow_untyped_defs，
其余 strict 项仍全局生效；override 名单写入 TECH_DEBT 跟踪。
pre-commit mypy hook 启用；make check 加 mypy 行。
src/ 仅做必要的类型注解补全与真 bug 修复（如有）。

Owning spec: docs/superpowers/specs/active/2026-05-10-tests-and-lint-production-grade-design-cn.md
Phase: 3/6

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

### Phase 3 verification

- [ ] **Step 3.V.1: 完整验证**

```bash
make check
uv run pytest -q
uv run mypy src
uv run pre-commit run --all-files 2>&1 | tail -10
```

输出粘贴到 verification 文件 P3 section。

---

## Phase 4 — OpenAPI 契约同源生成

**Goal:** `scripts/regen_openapi.py` 把 FastAPI `app.openapi()` 写到 `docs/generated/openapi.json`；前端 `web/src/api/types.ts` 由 `openapi-typescript` 生成；`tests/contract/test_openapi_drift.py` 对比仓库版本与重新生成的版本，差异即 fail；`make contract-check` 与 `make regen-contract` 实装。

### Task 4.1 — 写 `scripts/regen_openapi.py`

**Files:**
- Create: `scripts/regen_openapi.py`

- [ ] **Step 4.1.1: 写脚本**

```python
# scripts/regen_openapi.py
"""Regenerate docs/generated/openapi.json from FastAPI app.openapi().

This is the source of truth for front-end types (web/src/api/types.ts).
Run via `make regen-contract` to also regenerate the TS types.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "generated" / "openapi.json"

# Make src importable
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    from parallax.app.runtime.app import create_app  # type: ignore[import-not-found]

    # Build app without starting collector or DB-touching lifecycle
    app = create_app(start_collector=False)
    schema = app.openapi()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}: {len(json.dumps(schema))} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4.1.2: 跑一次生成 baseline openapi.json**

```bash
uv run python scripts/regen_openapi.py
ls -la docs/generated/openapi.json
head -20 docs/generated/openapi.json
```

Expected: 文件存在，JSON 头部含 `"openapi": "3.0.x"`。

### Task 4.2 — 安装 openapi-typescript 并生成 types.ts

**Files:**
- Modify: `web/package.json`（devDeps）
- Create: `web/src/api/types.ts`（生成产物）

- [ ] **Step 4.2.1: 装依赖**

```bash
cd web && npm install --save-dev openapi-typescript@^7; cd ..
```

- [ ] **Step 4.2.2: 生成 types.ts**

```bash
cd web && npm run generate:types; cd ..
ls -la web/src/api/types.ts
head -20 web/src/api/types.ts
```

Expected: 文件存在，含 `export interface paths {` 与 `export interface components {` 等。

- [ ] **Step 4.2.3: 验证 ESLint ignores 正确（types.ts 不应被 lint 抓）**

```bash
cd web && npm run lint; cd ..
# exit 0
```

如果 lint 警告 types.ts，确认 `web/eslint.config.js` 的 `ignores` 含 `src/api/types.ts`。

### Task 4.3 — 写契约漂移测试（TDD：先 failing，再让其 pass）

**Files:**
- Create: `tests/contract/test_openapi_drift.py`

- [ ] **Step 4.3.1: 先写测试（应当通过，因为 P4.1/P4.2 已经把 baseline 写入仓库）**

```python
# tests/contract/test_openapi_drift.py
"""Contract test: regenerate OpenAPI + frontend types and assert no drift.

If this test fails, run `make regen-contract` to update the committed artefacts,
then commit the resulting diff so reviewers can see the schema change.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
OPENAPI_PATH = ROOT / "docs" / "generated" / "openapi.json"
TYPES_PATH = ROOT / "web" / "src" / "api" / "types.ts"


@pytest.mark.contract
def test_openapi_json_matches_committed_artefact(tmp_path: Path) -> None:
    """Regenerate openapi.json into a tmp dir and compare bytes with the committed one."""
    from parallax.app.runtime.app import create_app

    app = create_app(start_collector=False)
    fresh = json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"
    committed = OPENAPI_PATH.read_text(encoding="utf-8")
    if fresh != committed:
        diff_path = tmp_path / "openapi.fresh.json"
        diff_path.write_text(fresh, encoding="utf-8")
        pytest.fail(
            "OpenAPI schema drifted from docs/generated/openapi.json.\n"
            f"Run `make regen-contract` to update the committed artefacts.\n"
            f"Fresh schema written to {diff_path} for inspection."
        )


@pytest.mark.contract
def test_frontend_types_match_openapi(tmp_path: Path) -> None:
    """Regenerate web/src/api/types.ts and compare with the committed one."""
    fresh_path = tmp_path / "types.ts"
    result = subprocess.run(
        [
            "npx",
            "openapi-typescript",
            str(OPENAPI_PATH),
            "-o",
            str(fresh_path),
        ],
        cwd=str(ROOT / "web"),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.fail(
            "openapi-typescript invocation failed.\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}\n"
            "Make sure `cd web && npm install` has run."
        )
    fresh = fresh_path.read_text(encoding="utf-8")
    committed = TYPES_PATH.read_text(encoding="utf-8")
    if fresh != committed:
        pytest.fail(
            f"Frontend types drifted from {TYPES_PATH.relative_to(ROOT)}.\n"
            "Run `make regen-contract` to update the committed artefacts."
        )
```

- [ ] **Step 4.3.2: 跑测试**

```bash
uv run pytest tests/contract -v 2>&1 | tail -10
```

Expected: 2 passed（因为 baseline 在 P4.1/P4.2 刚生成）。

- [ ] **Step 4.3.3: 验证测试能抓漂移（人工诱导一次）**

```bash
echo '{"drift": true}' >> docs/generated/openapi.json
uv run pytest tests/contract -v 2>&1 | tail -10
```

Expected: `test_openapi_json_matches_committed_artefact` failed，错误消息含 "Run `make regen-contract`"。

恢复：

```bash
uv run python scripts/regen_openapi.py
uv run pytest tests/contract -v 2>&1 | tail -3
# 2 passed
```

### Task 4.4 — `make contract-check` 与 `make regen-contract` 实装

**Files:**
- Modify: `Makefile`

- [ ] **Step 4.4.1: 替换 contract-check 与 regen-contract 占位行**

```makefile
contract-check: ## verify OpenAPI types are in sync (gate 2)
	@uv run python -m pytest tests/contract -m contract

regen-contract: ## regenerate openapi.json + web/src/api/types.ts
	@uv run python scripts/regen_openapi.py
	@cd web && npm run generate:types && cd ..
```

- [ ] **Step 4.4.2: 跑两个 target 验证**

```bash
make regen-contract
make contract-check
```

Expected: 都退出 0。

### Task 4.5 — Phase 4 commit

- [ ] **Step 4.5.1: 提交**

```bash
git add scripts/regen_openapi.py docs/generated/openapi.json web/package.json web/package-lock.json web/src/api/types.ts tests/contract/test_openapi_drift.py Makefile
git status --short | head -10
git commit -m "$(cat <<'EOF'
test: OpenAPI contract drift gate (P4)

scripts/regen_openapi.py: 从 FastAPI app.openapi() 生成 docs/generated/openapi.json。
web/src/api/types.ts: 由 openapi-typescript 生成；入仓便于 review。
tests/contract/test_openapi_drift.py: 重新生成两份产物，与仓库内容对比；
不一致 fail 并打印 `make regen-contract` 修复指引（第十讲 agent-friendly 错误）。
Makefile: contract-check/regen-contract 实装。

Owning spec: docs/superpowers/specs/active/2026-05-10-tests-and-lint-production-grade-design-cn.md
Phase: 4/6

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

### Phase 4 verification

- [ ] **Step 4.V.1: 完整验证**

```bash
make contract-check
make check
```

输出粘贴到 verification 文件 P4 section。

---

## Phase 5 — e2e harness（testcontainers + uvicorn subprocess）

**Goal:** `tests/e2e/conftest.py` 提供 `e2e_postgres` / `e2e_uvicorn` / `e2e_writer` 三个 session-scope fixture；`tests/e2e/test_golden_path.py` 跑 5 个运行时断言；PG 不可达 fail-loud（带修复指引），可用 `SKIP_E2E=1` 显式跳过；`make test-e2e` 实装。

### Task 5.1 — 安装 testcontainers + websockets

**Files:**
- Modify: `pyproject.toml`（dev deps）

- [ ] **Step 5.1.1: dev deps 加 testcontainers + websockets**

```toml
[dependency-groups]
dev = [
    "pytest>=8.3.0",
    "ruff>=0.8.6",
    "pre-commit>=3.7",
    "mypy>=1.13",
    "testcontainers[postgres]>=4.8",
    "websockets>=12.0",
]
```

注意 `websockets` 已在主依赖里，这里加到 dev 是显式表达 e2e 测试也需要它。如果重复声明导致 uv 警告，从 dev deps 删除即可。

跑：

```bash
uv sync
```

### Task 5.2 — 写 `tests/e2e/_uvicorn_entry.py`

**Files:**
- Create: `tests/e2e/_uvicorn_entry.py`

- [ ] **Step 5.2.1: 写入口脚本**

```python
# tests/e2e/_uvicorn_entry.py
"""Entrypoint for the e2e uvicorn subprocess.

Run as:
  python -m tests.e2e._uvicorn_entry --port 0

Reads PARALLAX_POSTGRES_DSN from env. Starts the FastAPI app with start_collector=False
so no upstream WebSocket is attempted. Prints the bound port to stdout once ready
in the form `READY port=12345` so the parent test process can parse it.
"""

from __future__ import annotations

import argparse
import os
import sys

import uvicorn


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()

    if "PARALLAX_POSTGRES_DSN" not in os.environ:
        print("FATAL: PARALLAX_POSTGRES_DSN not set", file=sys.stderr)
        return 1

    # Import after env validation
    from parallax.app.runtime.app import create_app  # type: ignore[import-not-found]

    app = create_app(start_collector=False)

    # uvicorn.Config + Server lets us bind port 0 then learn the actual port
    config = uvicorn.Config(app, host="127.0.0.1", port=args.port, log_level="warning")
    server = uvicorn.Server(config)

    # Hook server startup to print the bound port for parent
    original_startup = server.startup

    async def _startup_with_port() -> None:
        await original_startup()
        for srv in server.servers:
            for sock in srv.sockets:
                bound_port = sock.getsockname()[1]
                print(f"READY port={bound_port}", flush=True)

    server.startup = _startup_with_port  # type: ignore[method-assign]
    server.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

### Task 5.3 — 写 `tests/e2e/_writer_entry.py`

**Files:**
- Create: `tests/e2e/_writer_entry.py`

- [ ] **Step 5.3.1: 写 sidecar writer 入口**

```python
# tests/e2e/_writer_entry.py
"""Entrypoint for the e2e writer sidecar process.

Run as:
  python -m tests.e2e._writer_entry --event-id <id> --text <text>

Reads PARALLAX_POSTGRES_DSN from env. Calls IngestService.ingest_event() with a
synthetic TwitterEvent and exits. Stdout: 'INGESTED <event_id>'.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-id", required=True)
    parser.add_argument("--text", required=True)
    parser.add_argument("--author", default="e2e_test")
    args = parser.parse_args()

    if "PARALLAX_POSTGRES_DSN" not in os.environ:
        print("FATAL: PARALLAX_POSTGRES_DSN not set", file=sys.stderr)
        return 1

    # Use the same app wiring path as production to ensure the writer goes through
    # the real IngestService -> repository chain.
    from parallax.app.runtime.app import _build_runtime  # type: ignore[import-not-found]
    from parallax.platform.config.settings import load_settings  # type: ignore[import-not-found]
    from parallax.domains.evidence.interfaces import (  # type: ignore[import-not-found]
        Author,
        Content,
        Source,
        TwitterEvent,
    )

    settings = load_settings()
    runtime = _build_runtime(settings, start_collector=False)

    event = TwitterEvent(
        event_id=args.event_id,
        author=Author(handle=args.author, display_name=args.author),
        content=Content(text=args.text, urls=[], hashtags=[], mentions=[], media_urls=[]),
        source=Source(kind="post", original_url=f"https://x.com/{args.author}/status/{args.event_id}"),
        observed_at=datetime.now(UTC),
        reference=None,
    )
    runtime.evidence.ingest_service.ingest_event(event, is_watched=False)
    print(f"INGESTED {args.event_id}", flush=True)
    return 0
```

注意：本脚本依赖 `_build_runtime` 与 `runtime.evidence.ingest_service` 这条路径。具体属性名可能与代码不一致；P5 实施时需要 `grep -n "ingest_service\|evidence" src/parallax/app/runtime/app.py` 验证并按实际名称调整。**写代码前必须先 grep 确认**。

- [ ] **Step 5.3.2: 验证 `_build_runtime` 路径**

```bash
grep -n "_build_runtime\|ingest_service\|class CliRuntime" src/parallax/app/runtime/app.py | head -20
```

如果 `runtime.evidence.ingest_service` 不存在，按实际属性名修改 `_writer_entry.py`。可能的形态：`runtime.ingest_service`、`runtime.services.ingest_service` 等。

### Task 5.4 — 写 `tests/e2e/conftest.py`

**Files:**
- Modify: `tests/e2e/conftest.py`（替换 P0 的占位）

- [ ] **Step 5.4.1: 替换为完整 fixture 套件**

```python
# tests/e2e/conftest.py
"""End-to-end test fixtures.

Three session-scope fixtures:
- e2e_postgres: testcontainers Postgres + alembic upgrade head
- e2e_uvicorn: subprocess running tests/e2e/_uvicorn_entry.py against e2e_postgres
- e2e_writer: callable that runs tests/e2e/_writer_entry.py to inject a synthetic event

Setting SKIP_E2E=1 in the environment skips e2e tests with an explicit reason.
"""

from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = ROOT / "alembic.ini"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for item in items:
        if "tests/e2e/" in str(item.fspath):
            item.add_marker(pytest.mark.e2e)


def _docker_available() -> bool:
    return shutil.which("docker") is not None and (
        subprocess.run(["docker", "info"], capture_output=True).returncode == 0
    )


@pytest.fixture(scope="session")
def e2e_postgres() -> Iterator[str]:
    """Yield a Postgres DSN backed by testcontainers; alembic-migrated."""
    if os.environ.get("SKIP_E2E") == "1":
        pytest.skip("SKIP_E2E=1 set; e2e tests skipped (this run cannot serve as verification evidence)")
    if not _docker_available():
        pytest.fail(
            "e2e tests require docker but `docker info` failed. Fix options:\n"
            "  1. Start Docker Desktop / colima / OrbStack and rerun.\n"
            "  2. Provide an external Postgres at GMGN_E2E_POSTGRES_DSN (TODO: support).\n"
            "  3. If you intentionally cannot run e2e, set SKIP_E2E=1 — but then this\n"
            "     run cannot count as a verification artefact.",
            pytrace=False,
        )

    from testcontainers.postgres import PostgresContainer  # type: ignore[import-not-found]

    with PostgresContainer("postgres:16-alpine") as pg:
        dsn = pg.get_connection_url().replace("postgresql+psycopg2://", "postgresql://")
        # alembic upgrade
        env = {**os.environ, "PARALLAX_POSTGRES_DSN": dsn, "PYTHONPATH": str(ROOT / "src")}
        result = subprocess.run(
            ["uv", "run", "alembic", "-c", str(ALEMBIC_INI), "upgrade", "head"],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            pytest.fail(
                f"alembic upgrade head failed against testcontainers PG.\n"
                f"stdout: {result.stdout}\n"
                f"stderr: {result.stderr}",
                pytrace=False,
            )
        yield dsn


def _wait_for_port_in_stdout(proc: subprocess.Popen[str], timeout: float = 30.0) -> int:
    deadline = time.monotonic() + timeout
    pattern = re.compile(r"^READY port=(\d+)$")
    assert proc.stdout is not None
    while time.monotonic() < deadline:
        line = proc.stdout.readline()
        if not line:
            if proc.poll() is not None:
                raise RuntimeError(f"uvicorn subprocess exited early (rc={proc.returncode})")
            continue
        match = pattern.match(line.strip())
        if match:
            return int(match.group(1))
    raise TimeoutError(f"uvicorn did not signal READY within {timeout}s")


def _wait_for_readyz(url: str, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    last_err: Exception | None = None
    while time.monotonic() < deadline:
        try:
            r = httpx.get(url, timeout=2.0)
            if r.status_code == 200:
                return
        except Exception as e:  # noqa: BLE001 -- e2e setup tolerates any error during boot
            last_err = e
        time.sleep(0.5)
    raise TimeoutError(f"{url} did not return 200 within {timeout}s; last_err={last_err}")


@pytest.fixture(scope="session")
def e2e_uvicorn(e2e_postgres: str) -> Iterator[str]:
    """Spawn uvicorn in a subprocess; yield base URL like http://127.0.0.1:PORT."""
    env = {
        **os.environ,
        "PARALLAX_POSTGRES_DSN": e2e_postgres,
        "PYTHONPATH": str(ROOT / "src"),
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "tests.e2e._uvicorn_entry", "--port", "0"],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    try:
        port = _wait_for_port_in_stdout(proc)
        base_url = f"http://127.0.0.1:{port}"
        _wait_for_readyz(f"{base_url}/readyz")
        yield base_url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


@pytest.fixture(scope="session")
def e2e_writer(e2e_postgres: str) -> Callable[[str, str], None]:
    """Callable: writer(event_id, text) injects one synthetic mention via IngestService."""

    def _write(event_id: str, text: str) -> None:
        env = {
            **os.environ,
            "PARALLAX_POSTGRES_DSN": e2e_postgres,
            "PYTHONPATH": str(ROOT / "src"),
        }
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tests.e2e._writer_entry",
                "--event-id",
                event_id,
                "--text",
                text,
            ],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"writer subprocess failed (rc={result.returncode}).\n"
                f"stdout: {result.stdout}\n"
                f"stderr: {result.stderr}"
            )

    return _write
```

注意 `httpx` 已在主依赖。

### Task 5.5 — 写 `tests/e2e/test_golden_path.py`

**Files:**
- Create: `tests/e2e/test_golden_path.py`

- [ ] **Step 5.5.1: 写测试（断言 §6.4 五条）**

```python
# tests/e2e/test_golden_path.py
"""Golden-path end-to-end test.

Asserts the 5 runtime signals from spec §6.4:
1. /readyz returns 200 + Postgres probe ok (app is ready)
2. e2e_writer injects 1 mention -> writer exits 0 + DB row appears (critical path + side effect)
3. /api/recent returns the injected mention (cross-process read)
4. WebSocket /ws/live receives a push within 5s of a follow-up writer (async propagation)
5. Resource cleanup is implicit (testcontainers ryuk + subprocess.terminate in conftest)
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Callable

import httpx
import psycopg
import pytest
import websockets


@pytest.mark.e2e
def test_golden_path_readyz(e2e_uvicorn: str) -> None:
    """Step 1: /readyz returns 200."""
    r = httpx.get(f"{e2e_uvicorn}/readyz", timeout=5.0)
    assert r.status_code == 200, f"readyz body: {r.text}"


@pytest.mark.e2e
def test_golden_path_writer_persists_to_db(
    e2e_postgres: str,
    e2e_writer: Callable[[str, str], None],
) -> None:
    """Step 2: writer subprocess writes a row visible from a separate connection."""
    event_id = f"e2e-{uuid.uuid4().hex[:12]}"
    text = "$E2E test mention for golden path"
    e2e_writer(event_id, text)

    with psycopg.connect(e2e_postgres) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM evidence WHERE event_id = %s", (event_id,))
        (count,) = cur.fetchone() or (0,)
        assert count >= 1, f"expected ≥1 evidence row for {event_id}, got {count}"


@pytest.mark.e2e
def test_golden_path_recent_returns_writer_event(
    e2e_uvicorn: str,
    e2e_writer: Callable[[str, str], None],
) -> None:
    """Step 3: /api/recent (cross-process read) sees the injected event."""
    event_id = f"e2e-{uuid.uuid4().hex[:12]}"
    e2e_writer(event_id, f"$RECENT {event_id}")
    r = httpx.get(f"{e2e_uvicorn}/api/recent?limit=50", timeout=5.0)
    assert r.status_code == 200, r.text
    payload = r.json()
    items = payload.get("items") or payload.get("events") or payload
    matched = [item for item in items if event_id in json.dumps(item)]
    assert matched, f"recent endpoint did not return event_id={event_id}; payload={payload}"


@pytest.mark.e2e
def test_golden_path_websocket_pushes_after_writer(
    e2e_uvicorn: str,
    e2e_writer: Callable[[str, str], None],
) -> None:
    """Step 4: WS /ws/live receives a push within 5s of a follow-up ingest."""
    event_id = f"e2e-{uuid.uuid4().hex[:12]}"
    ws_url = e2e_uvicorn.replace("http://", "ws://") + "/ws/live"

    async def _run() -> None:
        async with websockets.connect(ws_url) as ws:  # type: ignore[attr-defined]
            # Allow the server to register the subscription
            await asyncio.sleep(0.3)
            e2e_writer(event_id, f"$WS push for {event_id}")
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
            except TimeoutError:
                pytest.fail(f"WS did not push within 5s after writer; event_id={event_id}")
            assert event_id in msg or "event" in msg.lower(), f"unexpected ws message: {msg!r}"

    asyncio.run(_run())
```

注意：
- `evidence` 表名与字段名 (`event_id`)、`/api/recent` 路径、WS 路径都已在 P5 准备阶段从代码确认（`src/parallax/app/surfaces/api/http.py:83` 与 `app/surfaces/api/ws.py`）。如实际 WS 路径不是 `/ws/live`，按代码实际路径替换。
- `payload.get("items") or payload.get("events") or payload` 这种 fallback 是因为本 plan 撰写时未抓 `/api/recent` 的精确返回 shape；P5 实施时跑一次 `httpx.get(...).json()` 印出来再固化字段名。

- [ ] **Step 5.5.2: 跑 e2e**

```bash
uv run pytest tests/e2e -v 2>&1 | tail -30
```

Expected: 4 passed（首次会拉 `postgres:16-alpine` 镜像，可能耗 30-60s）。如有 fail，按错误消息修：
- 路径不对：grep 实际路由
- DB 字段名不对：grep `class Evidence`、检 alembic 迁移
- WS 协议不对：读 `app/surfaces/api/ws.py` 确认握手与消息格式

- [ ] **Step 5.5.3: 测试 SKIP_E2E 路径**

```bash
SKIP_E2E=1 uv run pytest tests/e2e -v 2>&1 | tail -10
```

Expected: 4 skipped，原因 `SKIP_E2E=1 set; ...`。

### Task 5.7b — Integration 也接 testcontainers（满足 spec AC5）

Spec §10 AC5 要求：PG 不可达时 `make check-all` 自动起 testcontainers，**对 integration 测试也生效**，不仅 e2e。当前 `tests/postgres_test_utils.py` 在 PG 不可达时仍 silent skip，需要在 integration conftest 用 fixture 强制接管。

**Files:**
- Modify: `tests/integration/conftest.py`（替换 P0 的占位）

- [ ] **Step 5.7b.1: 把 `tests/integration/conftest.py` 改为完整版**

```python
# tests/integration/conftest.py
"""Integration-test fixtures.

Session-scope `_ensure_postgres_dsn` runs once per pytest invocation:
- If GMGN_TEST_POSTGRES_DSN is reachable, use it (existing behavior, fastest).
- Else if SKIP_INTEGRATION=1, skip entire suite (cannot serve as verification evidence).
- Else spin testcontainers Postgres + alembic upgrade head, point GMGN_TEST_POSTGRES_DSN at it.
- Else fail loud with repair instructions.

This makes tests/postgres_test_utils.py's connect_postgres_test() find a usable DSN
in all cases, so individual integration tests no longer silently skip.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest

ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = ROOT / "alembic.ini"

DEFAULT_DSN = "postgresql://postgres:postgres@127.0.0.1:55432/parallax_test"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for item in items:
        if "tests/integration/" in str(item.fspath):
            item.add_marker(pytest.mark.integration)


def _dsn_reachable(dsn: str) -> bool:
    try:
        with psycopg.connect(dsn, connect_timeout=2):
            return True
    except Exception:  # noqa: BLE001 -- probing only
        return False


def _docker_available() -> bool:
    return shutil.which("docker") is not None and (
        subprocess.run(["docker", "info"], capture_output=True).returncode == 0
    )


@pytest.fixture(scope="session", autouse=True)
def _ensure_postgres_dsn() -> Iterator[None]:
    """Ensure tests/postgres_test_utils.connect_postgres_test() finds a usable DSN.

    Mutates os.environ["GMGN_TEST_POSTGRES_DSN"] for the entire session.
    """
    existing = os.environ.get("GMGN_TEST_POSTGRES_DSN", DEFAULT_DSN)

    if _dsn_reachable(existing):
        os.environ["GMGN_TEST_POSTGRES_DSN"] = existing
        yield
        return

    if os.environ.get("SKIP_INTEGRATION") == "1":
        pytest.skip(
            "SKIP_INTEGRATION=1 set; integration tests skipped (this run cannot serve as verification evidence)",
            allow_module_level=True,
        )

    if not _docker_available():
        pytest.fail(
            "Integration tests require a reachable Postgres but none was found. Fix options:\n"
            f"  1. Start your local test DB at {existing} (e.g. `docker compose up -d postgres`).\n"
            "  2. Provide an alternate DSN: GMGN_TEST_POSTGRES_DSN=postgresql://...\n"
            "  3. Start Docker Desktop / colima / OrbStack and rerun (testcontainers will auto-spin).\n"
            "  4. If you intentionally cannot run integration, set SKIP_INTEGRATION=1 — but then\n"
            "     this run cannot count as a verification artefact (DoD: see docs/WORKFLOW.md).",
            pytrace=False,
        )

    # Spin testcontainers
    from testcontainers.postgres import PostgresContainer  # type: ignore[import-not-found]

    with PostgresContainer("postgres:16-alpine") as pg:
        dsn = pg.get_connection_url().replace("postgresql+psycopg2://", "postgresql://")
        env = {**os.environ, "PARALLAX_POSTGRES_DSN": dsn, "PYTHONPATH": str(ROOT / "src")}
        result = subprocess.run(
            ["uv", "run", "alembic", "-c", str(ALEMBIC_INI), "upgrade", "head"],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            pytest.fail(
                f"alembic upgrade head failed against testcontainers PG.\n"
                f"stdout: {result.stdout}\n"
                f"stderr: {result.stderr}",
                pytrace=False,
            )
        os.environ["GMGN_TEST_POSTGRES_DSN"] = dsn
        yield
```

- [ ] **Step 5.7b.2: 验证 PG 可达时 integration 跑通（无回归）**

```bash
# 假设本地 PG 在 127.0.0.1:55432 可达（compose 已起）
make test-integration 2>&1 | tail -10
```

Expected: 全 pass，无 skipped（除非个别用例自身 skip）。如果之前是 `136 skipped`，现在应几乎无 skip。

- [ ] **Step 5.7b.3: 验证 PG 不可达 + docker 可用时自动起 testcontainers**

```bash
# 临时停掉本地 PG（如果用 compose 起的）
docker compose stop postgres 2>/dev/null || true
# 或临时改 DSN
GMGN_TEST_POSTGRES_DSN=postgresql://nobody@127.0.0.1:1/nodb make test-integration 2>&1 | tail -15
```

Expected: 看到 testcontainers 起一个临时容器（"Pulling image postgres:16-alpine" 或类似日志），然后跑 integration 全 pass。

恢复：

```bash
docker compose start postgres 2>/dev/null || true
unset GMGN_TEST_POSTGRES_DSN
```

- [ ] **Step 5.7b.4: 验证 PG 不可达 + SKIP_INTEGRATION=1 路径**

```bash
SKIP_INTEGRATION=1 GMGN_TEST_POSTGRES_DSN=postgresql://nobody@127.0.0.1:1/nodb make test-integration 2>&1 | tail -10
```

Expected: 整个 integration suite skipped，输出含 "SKIP_INTEGRATION=1 set"。

- [ ] **Step 5.7b.5: 验证 PG 不可达 + docker 不可用时 fail-loud**

```bash
# 停掉 docker daemon（或在 docker 不可用环境）；如果跑不了这一步，跳过手动验证
GMGN_TEST_POSTGRES_DSN=postgresql://nobody@127.0.0.1:1/nodb make test-integration 2>&1 | tail -15
```

Expected: 退出非 0，stderr 含 4 条修复指引。

### Task 5.6 — `make test-e2e` 实装 + `make check-all` 串接 e2e

**Files:**
- Modify: `Makefile`

- [ ] **Step 5.6.1: `test-e2e` 已经在 P0 占位且现在能跑；验证它**

```bash
make test-e2e
```

Expected: 跑 `tests/e2e/`，4 passed。

- [ ] **Step 5.6.2: `check-all` 已经在 P0 串了 `test-integration` 和 `test-e2e`，验证整体**

```bash
time make check-all
```

Expected: 退出 0；耗时记录。如果 > 120s（spec AC3 上限），检查是否某 fixture 没复用 session-scope。

### Task 5.7 — Phase 5 commit

- [ ] **Step 5.7.1: 提交**

```bash
git add pyproject.toml tests/e2e/ tests/integration/conftest.py Makefile
git status --short | head -10
git commit -m "$(cat <<'EOF'
test: cross-process e2e harness + integration auto-testcontainers (P5)

testcontainers[postgres] + websockets dev deps；
tests/e2e/_uvicorn_entry.py + _writer_entry.py 是测试专用入口；
tests/e2e/conftest.py 提供 e2e_postgres / e2e_uvicorn / e2e_writer fixture；
tests/e2e/test_golden_path.py 断言 5 个运行时信号（spec §6.4）；
tests/integration/conftest.py 在 PG 不可达时自动起 testcontainers，
满足 spec AC5 fail-loud + 修复指引；SKIP_INTEGRATION=1 / SKIP_E2E=1 显式
跳过通道（任一启用则该次运行不可作为 verification 证据）。

Owning spec: docs/superpowers/specs/active/2026-05-10-tests-and-lint-production-grade-design-cn.md
Phase: 5/6

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

### Phase 5 verification

- [ ] **Step 5.V.1: 完整验证**

```bash
make test-e2e
time make check-all
```

输出粘贴到 verification 文件 P5 section（含首次镜像拉取耗时单独标注）。

---

## Phase 6 — 覆盖率门槛 + DoD 治理 + 自我证据

**Goal:** `pytest-cov` + `coverage` 配置 + `fail_under = 80` + branch coverage；`make coverage` / `make check-all` 加 coverage gate；`docs/superpowers/_templates/verification-template.md` 增加三段强制；`docs/WORKFLOW.md` 与 `docs/TESTING.md` 同步引用 `make check-all`；`tests/architecture/test_completion_gates.py` grep 校验同步；本 spec 自身的 verification artefact 用新模板写完。

### Task 6.1 — 安装 pytest-cov + 配置 coverage

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 6.1.1: dev deps 加 pytest-cov**

```toml
[dependency-groups]
dev = [
    "pytest>=8.3.0",
    "pytest-cov>=5.0",
    "ruff>=0.8.6",
    "pre-commit>=3.7",
    "mypy>=1.13",
    "testcontainers[postgres]>=4.8",
    "websockets>=12.0",
]
```

- [ ] **Step 6.1.2: 加 coverage 配置**

在 `pyproject.toml` 末尾追加：

```toml
[tool.coverage.run]
branch = true
source = ["src/parallax"]
omit = [
  "src/parallax/platform/db/alembic/versions/*",
  "src/parallax/cli.py",  # CLI exercised by integration smoke; not unit-coverable
]

[tool.coverage.report]
show_missing = true
skip_empty = true
precision = 1
fail_under = 80
exclude_lines = [
  "pragma: no cover",
  "raise NotImplementedError",
  "if TYPE_CHECKING:",
  "\\.\\.\\.",  # protocol bodies
]
```

- [ ] **Step 6.1.3: 跑一次 baseline 看实测覆盖率**

```bash
uv sync
uv run pytest --cov --cov-report=term-missing --cov-config=pyproject.toml 2>&1 | tail -30
```

记下 `TOTAL` 行的 line% 与 branch%。如果 line% < 80%，先把 `fail_under` 调到实测值-2%（spec §11 风险条款允许，但要在 verification artefact 中说明）。例如实测 72%，则 `fail_under = 70`，并在 TECH_DEBT 写 follow-up "把覆盖率从 70% 抬到 80%"。

如果 line% 已 ≥ 80%，保持 `fail_under = 80`。

### Task 6.2 — `make coverage` 与 `make check-all` 接覆盖率

**Files:**
- Modify: `Makefile`

- [ ] **Step 6.2.1: 替换 `coverage` 占位行**

```makefile
coverage: ## run coverage report (gates fail_under from pyproject.toml [tool.coverage])
	@uv run python -m pytest --cov --cov-report=term-missing --cov-config=pyproject.toml -q
```

注意：`pytest-cov` 默认会 honor `[tool.coverage.report] fail_under`，达不到自动退出非 0。

- [ ] **Step 6.2.2: 验证**

```bash
make coverage
```

Expected: 退出 0（如果 baseline 达标）。打印 line%/branch%/missing 表。

- [ ] **Step 6.2.3: 验证 `make check-all` 整体**

```bash
time make check-all
```

Expected: 退出 0；最后一行输出含 coverage 结果。

### Task 6.3 — 升级 verification-template.md

**Files:**
- Modify: `docs/superpowers/_templates/verification-template.md`

- [ ] **Step 6.3.1: 替换原 `## Verification commands` 章节为新的强制三段**

把 `verification-template.md:27-45` 的整段（`## Verification commands` 到 `Other commands run ...` 段末）替换为：

```markdown
## Verification commands

The only command whose output may be pasted as evidence is `make check-all`.
Paste the FULL output below, including the exit code line.

```text
$ make check-all
<paste full stdout/stderr here>
exit code: 0
```

If `make check-all` exit code is non-zero, the work is not complete — do not
file this artefact until it is.

## Coverage

| metric | value | threshold | status |
|--------|-------|-----------|--------|
| line   | X.X%  | ≥ 80%     | ✅/❌  |
| branch | X.X%  | ≥ 70%     | ✅/❌  |

If thresholds were temporarily relaxed in `pyproject.toml [tool.coverage.report]`,
state the relaxed value and the follow-up entry in `docs/TECH_DEBT.md`.

## Skipped tests

Number of skipped tests in the run above: <N>

If N > 0, list categories and explain why each is acceptable:

| count | reason | acceptable? |
|-------|--------|-------------|
|       |        |             |

A run with unexplained skips cannot serve as completion evidence.

## E2E golden path

Confirm each runtime signal from the spec §6.4 was asserted:

- [ ] /readyz returned 200
- [ ] writer wrote a row visible to a separate process
- [ ] /api/recent returned the injected event
- [ ] WS /ws/live pushed within 5s
- [ ] testcontainers PG and uvicorn subprocess cleaned up

If `SKIP_E2E=1` was set, this run cannot serve as completion evidence.

## Other commands run (manual UI smoke; only for areas not coverable by tests)

```text
$ <command>
<output>
```
```

### Task 6.4 — 更新 `docs/TESTING.md` 与 `docs/WORKFLOW.md`

**Files:**
- Modify: `docs/TESTING.md`、`docs/WORKFLOW.md`

- [ ] **Step 6.4.1: 替换 `docs/TESTING.md` 的 `## Completion verification` 章节**

把那一段（`docs/TESTING.md:18-26`）替换为：

```markdown
## Completion verification

Before claiming work is complete, run:

```bash
make check-all
```

This runs all three gates (lint+type, unit+architecture+contract, integration+e2e+coverage)
and is the only command whose output may be pasted as evidence in a verification artefact.
Exit code 0 + the new `Coverage`, `Skipped tests`, and `E2E golden path` sections in
`docs/superpowers/_templates/verification-template.md` are required.

UI flows that genuinely cannot be exercised by `make check-all` (subjective UX,
animations, real-network behaviour) must be exercised manually and recorded under
`Other commands run` in the verification template.
```

- [ ] **Step 6.4.2: 替换 `docs/WORKFLOW.md` 的 `## Completion gates` 章节**

把 `docs/WORKFLOW.md:34-41` 替换为：

```markdown
## Completion gates

Do not claim a task is complete, fixed, or passing until all of the following
are true and have been written into the verification artefact:

- The implementation matches the approved spec; deviations are documented.
- `make check-all` exited 0 in the worktree, AND the verification artefact contains
  its full output (no abridging) plus the new `Coverage`, `Skipped tests`, and
  `E2E golden path` sections.
- The diff was reviewed against the plan.
- UI flows genuinely outside `make check-all` coverage were exercised manually
  and recorded under `Other commands run`.
- Remaining risks and follow-ups are listed and, if non-trivial, appended to
  `docs/TECH_DEBT.md`.

If any of the above cannot be satisfied, surface the gap rather than claiming completion.
```

### Task 6.5 — 写 `tests/architecture/test_completion_gates.py`（grep 校验同步）

**Files:**
- Create: `tests/architecture/test_completion_gates.py`

- [ ] **Step 6.5.1: 写测试**

```python
# tests/architecture/test_completion_gates.py
"""Architecture test: completion-gate documents must reference the canonical command.

Catches the failure mode where someone updates docs/TESTING.md but not WORKFLOW.md
(or vice versa), or the verification template loses one of its required sections.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TESTING = ROOT / "docs" / "TESTING.md"
WORKFLOW = ROOT / "docs" / "WORKFLOW.md"
TEMPLATE = ROOT / "docs" / "superpowers" / "_templates" / "verification-template.md"


@pytest.mark.architecture
def test_testing_md_references_make_check_all() -> None:
    text = TESTING.read_text(encoding="utf-8")
    assert "make check-all" in text, (
        "docs/TESTING.md must reference `make check-all` as the canonical "
        "completion-verification entry."
    )


@pytest.mark.architecture
def test_workflow_md_references_make_check_all() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "make check-all" in text, (
        "docs/WORKFLOW.md must reference `make check-all` in its completion-gates section."
    )


@pytest.mark.architecture
def test_verification_template_has_three_required_sections() -> None:
    text = TEMPLATE.read_text(encoding="utf-8")
    for required in ("## Coverage", "## Skipped tests", "## E2E golden path"):
        assert required in text, (
            f"verification-template.md is missing required section `{required}`. "
            "Did docs/TESTING.md / WORKFLOW.md change without the template being updated?"
        )


@pytest.mark.architecture
def test_old_three_command_recipe_not_in_workflow() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    forbidden = "uv run ruff check ., uv run pytest, uv run python -m compileall"
    assert forbidden not in text, (
        "Old three-command recipe should be replaced with `make check-all`; "
        "found legacy phrase in docs/WORKFLOW.md."
    )
```

- [ ] **Step 6.5.2: 跑测试**

```bash
uv run pytest tests/architecture/test_completion_gates.py -v 2>&1 | tail -10
```

Expected: 4 passed。

### Task 6.6 — TECH_DEBT 写入 follow-up（如有）

**Files:**
- Modify: `docs/TECH_DEBT.md`

- [ ] **Step 6.6.1: 如果 P6.1.3 临时降低了 `fail_under`，写 follow-up**

在 `docs/TECH_DEBT.md` 末尾追加：

```markdown
## 测试覆盖率门槛追赶

- 当前 `pyproject.toml [tool.coverage.report] fail_under = <实测-2>`（来自 spec 2026-05-10-tests-and-lint-production-grade）。
- 目标：line ≥ 80% / branch ≥ 70%。
- 计划：每 sprint 抬升 fail_under 至少 2 个百分点，直到达标后锁死。
```

如果 P6.1.3 实测已 ≥ 80%，跳过本 step。

### Task 6.7 — 写本 spec 自身的 verification artefact

**Files:**
- Modify: `docs/superpowers/plans/active/2026-05-10-tests-and-lint-production-grade-verification.md`

- [ ] **Step 6.7.1: 用新模板填本 spec 的 verification 文件**

复制 `docs/superpowers/_templates/verification-template.md` 的结构，填入：

- AC1 ~ AC10（spec §10）逐条 ✅/❌ + evidence
- `make check-all` 完整输出
- Coverage 表（实测值）
- Skipped tests 表
- E2E golden path 5 个 checkbox 全部勾上
- Diff summary（按本 plan 的 7 个 phase 各列 commit hash 与文件清单）
- Risks observed
- Follow-ups（mypy override 名单、coverage 追赶、OQ1/2/3 的 close 状态）

文件路径：`docs/superpowers/plans/active/2026-05-10-tests-and-lint-production-grade-verification.md`（已在 P-4 创建占位，这里完整写）。

### Task 6.8 — Phase 6 commit

- [ ] **Step 6.8.1: 提交**

```bash
git add pyproject.toml Makefile docs/TESTING.md docs/WORKFLOW.md docs/superpowers/_templates/verification-template.md tests/architecture/test_completion_gates.py docs/TECH_DEBT.md docs/superpowers/plans/active/2026-05-10-tests-and-lint-production-grade-verification.md
git status --short | head -20
git commit -m "$(cat <<'EOF'
chore: coverage gate + DoD canonicalization on make check-all (P6)

pytest-cov + [tool.coverage] line/branch + fail_under；make coverage 实装。
verification-template.md 增加 Coverage / Skipped tests / E2E golden path 三段强制。
docs/TESTING.md + docs/WORKFLOW.md 把 DoD 从三命令改为 make check-all 引用。
tests/architecture/test_completion_gates.py 用 grep 校验三份文档同步。
本 spec 自身的 verification artefact 用新模板完成。

Owning spec: docs/superpowers/specs/active/2026-05-10-tests-and-lint-production-grade-design-cn.md
Phase: 6/6

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

### Phase 6 verification

- [ ] **Step 6.V.1: 跑最终全量**

```bash
time make check-all
uv run pytest tests/architecture -v 2>&1 | tail -10
```

Expected: 全 0 退出；architecture 测试含新的 4 个 completion-gates 用例全 pass。

---

## Final verification

完成所有 phase 后：

- [ ] `make check-all` 退出 0
- [ ] `uv run pytest --collect-only -q` 显示 ≥ 567 用例（原 563 + 至少 4 新 completion_gates + 4 e2e + 2 contract drift）
- [ ] `find tests -maxdepth 1 -name 'test_*.py' | wc -l` = 0
- [ ] `ls tests/{unit,integration,e2e,architecture,contract,golden}/conftest.py` 全部存在
- [ ] `pre-commit run --all-files` 退出 0
- [ ] `time make check` < 60s，`time make check-all` < 180s（首次镜像拉取除外）
- [ ] `docs/superpowers/plans/active/2026-05-10-tests-and-lint-production-grade-verification.md` 含 `make check-all` 完整输出与 exit code = 0
- [ ] `docs/TECH_DEBT.md` 含 mypy override 名单（与可能的 coverage 追赶条目）
- [ ] 移动 spec 与 plan 到 `completed/`：

```bash
git mv docs/superpowers/specs/active/2026-05-10-tests-and-lint-production-grade-design-cn.md docs/superpowers/specs/completed/
git mv docs/superpowers/plans/active/2026-05-10-tests-and-lint-production-grade-plan-cn.md docs/superpowers/plans/completed/
git mv docs/superpowers/plans/active/2026-05-10-tests-and-lint-production-grade-verification.md docs/superpowers/plans/completed/
git commit -m "chore: archive tests-and-lint production-grade spec/plan/verification to completed/"
```

---

## PR breakdown

每个 phase 一个独立 PR，按顺序合并。前 PR 不合不开下一个 PR。

1. **PR 1 — P0 scaffolding**：tests/ 子目录、根 conftest、markers 注册、Makefile 占位 target。基线测试不变。
2. **PR 2 — P1 git mv**：`scripts/migrate_tests_layout.py` + 95 个文件位置变化。pytest 数量不变。
3. **PR 3 — P2 lint matrix**：ruff 规则扩 + ruff format + ESLint flat + Prettier + pre-commit。`make check` 退出 0。
4. **PR 4 — P3 mypy strict**：mypy 配置 + `domains/`/`platform/`/`cli.py` 类型修复 + TECH_DEBT 写 override。
5. **PR 5 — P4 OpenAPI 契约**：regen_openapi 脚本 + types.ts 生成 + drift 测试 + Makefile 实装。
6. **PR 6 — P5 e2e harness**：testcontainers/websockets dev deps + e2e 三 fixture + golden path 测试。
7. **PR 7 — P6 coverage + DoD**：pytest-cov + Makefile coverage + 模板 + WORKFLOW/TESTING 同步 + completion gates 测试 + 本 spec 自身 verification artefact。

---

## Rollout order

按 phase 顺序，每 phase 完成、跑通 verification、commit 后进入下一 phase。无需 alembic 迁移、无需 backfill、无需运行时操作。

---

## Rollback

| Phase | Rollback |
|---|---|
| P0 | `git revert <commit>` 一键回滚；空目录与 conftest 删除即可 |
| P1 | `git revert <commit>` —— git mv 是可逆的；revert 把所有 95 个文件移回根目录 |
| P2 | `git revert <commit>` —— pre-commit hook 由 `pre-commit uninstall` 卸载 |
| P3 | `git revert <commit>` —— mypy 添加的类型注解 revert 后代码运行时行为不变 |
| P4 | `git revert <commit>` —— `docs/generated/openapi.json` 与 `web/src/api/types.ts` 删除 |
| P5 | `git revert <commit>` —— testcontainers 容器在 ryuk 下自动清理；不留状态 |
| P6 | `git revert <commit>` —— 旧 DoD 文档与模板恢复；`fail_under` 从 pyproject 移除 |

如需把整套 spec 回退：

```bash
git revert <P6-commit> <P5-commit> <P4-commit> <P3-commit> <P2-commit> <P1-commit> <P0-commit>
# 或者直接：
git checkout main -- .
```

不会有任何运行时副作用（无 DB schema 变更、无运行 worker 状态变更）。

---

## Acceptance test commands（映射 spec §10）

| Spec AC | 验证命令 | 期望输出 |
|---|---|---|
| AC1 (目录分层) | `find tests -maxdepth 1 -name 'test_*.py' \| wc -l && ls tests/{unit,integration,e2e,architecture,contract,golden}/conftest.py` | `0` + 6 个 conftest.py 文件路径 |
| AC2 (marker 严格) | `uv run pytest --collect-only -q --markers \| head -20` | 列出 5 个注册 marker，无 unknown warning |
| AC3 (快慢路径) | `time make check && time make check-all` | check < 60s；check-all < 180s（exclu 镜像拉取） |
| AC4 (lint 升级) | `make check` | 退出 0 |
| AC5 (PG fail-loud) | 在 docker stop 后 `make check-all` | 非 0 退出，stderr 含 ≥ 3 条修复指引 |
| AC6 (e2e 黄金路径) | `uv run pytest tests/e2e -v` | 4 passed，每条断言有日志证据 |
| AC7 (OpenAPI 契约) | `make contract-check` 同步态：退出 0；`echo X >> docs/generated/openapi.json && make contract-check`：非 0 + 修复指引 | 验证两态 |
| AC8 (覆盖率门槛) | `make coverage` | 退出 0 + 打印 `line=X% branch=Y%` 与门槛比对 |
| AC9 (DoD 同步) | `uv run pytest tests/architecture/test_completion_gates.py -v` | 4 passed |
| AC10 (自我证据) | `cat docs/superpowers/plans/.../verification.md` | 含 `make check-all` 完整输出 + exit 0 |

## Verification

详见 `docs/superpowers/plans/active/2026-05-10-tests-and-lint-production-grade-verification.md`（P-4 创建占位，P0-P6 持续追加，P6.7 完整化）。
