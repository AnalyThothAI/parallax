#!/usr/bin/env python3
"""Generate the tracked backend per-file Kappa/CQRS audit ledger."""

from __future__ import annotations

import argparse
import ast
import hashlib
import re
import subprocess
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "docs/generated/backend-kappa-cqrs-file-ledger-2026-07-13.md"
SQL_TABLE_RE = re.compile(
    r"\b(?:FROM|JOIN|INSERT\s+INTO|(?<!FOR\s)UPDATE|DELETE\s+FROM)\s+([a-z_][a-z0-9_]*)",
    re.IGNORECASE,
)
SQL_CTE_RE = re.compile(
    r"(?:\bWITH\s+(?:RECURSIVE\s+)?|,)\s*([a-z_][a-z0-9_]*)"
    r"(?:\s*\([^)]*\))?\s+AS\s+(?:(?:NOT\s+)?MATERIALIZED\s+)?\(",
    re.IGNORECASE,
)
NON_TABLE_SQL_NAMES = frozenset({"case", "excluded", "lateral", "on", "set", "unnest"})
SQL_LINE_COMMENT_RE = re.compile(r"--[^\n]*")
SQL_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)


def _workspace_python_files() -> list[Path]:
    result = subprocess.run(
        [
            "git",
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
            "src/parallax/**/*.py",
            "src/parallax/*.py",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return sorted(ROOT / line for line in result.stdout.splitlines() if line and (ROOT / line).is_file())


def _module_name(path: Path) -> str:
    return ".".join(path.relative_to(ROOT / "src").with_suffix("").parts)


def _imports(source: str) -> set[str]:
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names if alias.name.startswith("parallax"))
        elif isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("parallax"):
            imported.add(node.module)
    return imported


def _sql_tables(source: str) -> set[str]:
    tables: set[str] = set()
    sql_values: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        value = SQL_BLOCK_COMMENT_RE.sub("", SQL_LINE_COMMENT_RE.sub("", node.value))
        if not re.search(r"\b(?:SELECT|INSERT|UPDATE|DELETE)\b", value, re.IGNORECASE):
            continue
        sql_values.append(value)
    cte_names = {name.lower() for value in sql_values for name in SQL_CTE_RE.findall(value)}
    for value in sql_values:
        for match in SQL_TABLE_RE.finditer(value):
            name = match.group(1).lower()
            following = value[match.end() :].lstrip()
            if name in cte_names or name in NON_TABLE_SQL_NAMES or following.startswith("("):
                continue
            tables.add(name)
    return tables


def _resolved_internal_imports(imports: set[str], modules: set[str]) -> set[str]:
    resolved: set[str] = set()
    for imported in imports:
        candidate = imported
        while candidate.startswith("parallax"):
            if candidate in modules:
                resolved.add(candidate)
                break
            if "." not in candidate:
                break
            candidate = candidate.rsplit(".", 1)[0]
    return resolved


def _domain_dependencies(imports: set[str]) -> str:
    domains = sorted(
        {
            parts[2]
            for imported in imports
            if len(parts := imported.split(".")) >= 3 and parts[:2] == ["parallax", "domains"]
        }
    )
    return ", ".join(domains) or "-"


def _classification(relative: Path) -> tuple[str, str, str]:
    parts = relative.parts
    stem = relative.stem
    if "alembic" in parts and "versions" in parts:
        return "schema-history", "迁移历史", "PostgreSQL schema 演进；不属于运行时兼容分支"
    if parts[:3] == ("src", "parallax", "integrations"):
        return "adapter", "外部适配器", "provider 输入/输出边界；不得拥有业务事实语义"
    if parts[:4] == ("src", "parallax", "app", "runtime"):
        if "worker_factories" in parts:
            return "composition", "worker 工厂", "配置/manifest 到唯一运行时 owner 的组装"
        if "worker" in stem:
            return "runtime", "worker 运行时", "worker 生命周期、wake/catch-up 或运行清单"
        return "runtime", "应用运行时", "进程组装、worker 注册、队列健康或运行控制"
    if parts[:4] == ("src", "parallax", "app", "surfaces"):
        surface = parts[4] if len(parts) > 4 else "surface"
        return "surface", f"{surface} 表面", "只读/命令边界；不得成为 read model 第二写者"
    if parts[:3] == ("src", "parallax", "platform"):
        if "db" in parts:
            return "platform", "数据库平台", "连接、事务、schema 或跨域队列基础设施"
        if "config" in parts:
            return "platform", "配置平台", "正式运行配置 schema 与加载边界"
        return "platform", "平台能力", "跨域基础设施；不得承载领域决策"
    if parts[:3] == ("src", "parallax", "domains") and len(parts) >= 4:
        domain = parts[3]
        if "runtime" in parts or "workers" in parts or stem.endswith("_worker"):
            return "domain-runtime", f"{domain} worker", "消费事实/控制队列并写该域唯一事实或读模型 owner"
        if "repositories" in parts or stem.endswith("_repository"):
            return "repository", f"{domain} repository", "PostgreSQL 事实、控制状态或读模型持久化边界"
        if "queries" in parts or stem.endswith("_query"):
            return "query", f"{domain} query", "无副作用查询/投影输入读取"
        if "read_models" in parts or "projection" in stem:
            return "projection", f"{domain} 投影", "从事实重建派生状态；稳定键且无变化零写入"
        if "providers" in parts or "provider" in stem:
            return "port", f"{domain} provider port", "领域所需 provider 能力契约"
        if "services" in parts or stem.endswith("_service"):
            return "service", f"{domain} service", "领域用例/事务编排；不绕过 repository owner"
        if "interfaces" in parts or stem in {"interfaces", "types"}:
            return "contract", f"{domain} 契约", "稳定领域类型、公开常量或协议"
        return "domain", f"{domain} 模块", "领域逻辑、模型或辅助边界"
    if stem == "__init__":
        return "package", "包声明", "Python 包边界"
    return "entrypoint", "入口", "服务/CLI 包入口"


def _markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def generate(output: Path, *, write: bool = True) -> str:
    files = _workspace_python_files()
    modules = {_module_name(path) for path in files}
    sources = {path: path.read_text(encoding="utf-8") for path in files}
    direct_imports = {path: _imports(source) for path, source in sources.items()}
    resolved_imports = {
        path: _resolved_internal_imports(imported, modules) for path, imported in direct_imports.items()
    }
    inbound = Counter(module for values in resolved_imports.values() for module in values)
    class_counts: Counter[str] = Counter()
    loc_total = 0
    rows: list[str] = []
    for path in files:
        relative = path.relative_to(ROOT)
        source = sources[path]
        loc = len(source.splitlines())
        loc_total += loc
        layer, role, chain = _classification(relative)
        class_counts[layer] += 1
        sql_tables = sorted(_sql_tables(source))
        table_summary = (
            f"{len(sql_tables)} historical table refs"
            if layer == "schema-history" and sql_tables
            else ", ".join(sql_tables) or "-"
        )
        digest = hashlib.sha256(source.encode()).hexdigest()[:12]
        module = _module_name(path)
        row_template = (
            "| `{path}` | {role} | {chain} | {domains} | {tables} | {inbound} / {outbound} | {loc} | `{digest}` |"
        )
        rows.append(
            row_template.format(
                path=relative.as_posix(),
                role=_markdown_cell(role),
                chain=_markdown_cell(chain),
                domains=_markdown_cell(_domain_dependencies(direct_imports[path])),
                tables=_markdown_cell(table_summary),
                inbound=inbound[module],
                outbound=len(resolved_imports[path]),
                loc=loc,
                digest=digest,
            )
        )
    distribution = "\n".join(f"| `{layer}` | {count} |" for layer, count in sorted(class_counts.items()))
    body = f"""# Backend Kappa/CQRS Per-file Ledger, 2026-07-13

本 ledger 覆盖当前工作树中所有 Git 跟踪或新增且实际存在的 `src/parallax/**/*.py` 文件。
它是逐文件审计的机械证据层：角色、Kappa/CQRS 链路职责、跨领域依赖、静态 SQL 表、
内部入/出依赖数、LOC 与 SHA-256 内容指纹。业务结论和修复记录见
`backend-kappa-cqrs-audit-2026-07-13.md`。

- 文件数：{len(files)}
- Python LOC：{loc_total}
- Alembic 迁移按 schema 历史保留，未误判为运行时兼容代码。
- `入/出依赖` 仅统计可解析的 `parallax.*` 静态 import；运行时注册、SQL、协议回调仍由主审计补充。
- 生成命令：`uv run python scripts/regen_backend_architecture_ledger.py`

## 分层分布

| 分类 | 文件数 |
|---|---:|
{distribution}

## 逐文件链路清单

| 文件 | 角色 | 链路责任 | 依赖领域 | 静态 SQL 表 | 入/出依赖 | LOC | 读取指纹 |
|---|---|---|---|---|---:|---:|---|
{chr(10).join(rows)}
"""
    if write:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(body, encoding="utf-8")
    return body


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    output = args.output if args.output.is_absolute() else ROOT / args.output
    generated = generate(output, write=not args.check)
    if args.check and (not output.exists() or output.read_text(encoding="utf-8") != generated):
        raise SystemExit("backend architecture ledger is stale")


if __name__ == "__main__":
    main()
