from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src" / "gmgn_twitter_intel"

DOMAINS = {
    "ingestion",
    "evidence",
    "asset_market",
    "token_intel",
    "social_enrichment",
    "closed_loop_harness",
    "notifications",
    "pulse_lab",
    "account_quality",
}

ALLOWED_ROOTS = {"app", "domains", "integrations", "platform"}
LEGACY_PACKAGES = {"collector", "pipeline", "retrieval", "storage", "market"}
SQL_ALLOWED_PARTS = {
    "repositories",
    "queries",
    "platform/db",
    "app/runtime",
}
SHIM_ALLOWED_FILES = {
    SRC_ROOT / "cli.py",
    SRC_ROOT / "__main__.py",
    SRC_ROOT / "api" / "app.py",
    SRC_ROOT / "api" / "http.py",
    SRC_ROOT / "api" / "ws.py",
}


def _python_files() -> list[Path]:
    return [
        path
        for path in SRC_ROOT.rglob("*.py")
        if "__pycache__" not in path.parts and "storage/alembic/versions" not in path.as_posix()
    ]


def _module(path: Path) -> str:
    return ".".join(path.relative_to(ROOT / "src").with_suffix("").parts)


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _imports(path: Path) -> list[str]:
    imports: list[str] = []
    module = _module(path)
    package_parts = module.split(".")[:-1]
    for node in ast.walk(_parse(path)):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        if isinstance(node, ast.ImportFrom):
            if node.module is None:
                continue
            if node.level:
                base = package_parts[: max(0, len(package_parts) - node.level + 1)]
                imports.append(".".join([*base, node.module]))
            else:
                imports.append(node.module)
    return [item for item in imports if item.startswith("gmgn_twitter_intel.")]


def _top_package(path: Path) -> str:
    parts = path.relative_to(SRC_ROOT).parts
    return parts[0] if parts else ""


def _domain_name(path: Path) -> str | None:
    parts = path.relative_to(SRC_ROOT).parts
    if len(parts) >= 2 and parts[0] == "domains":
        return parts[1]
    return None


def _is_sql_allowed(path: Path) -> bool:
    posix = path.relative_to(SRC_ROOT).as_posix()
    return any(part in posix for part in SQL_ALLOWED_PARTS)


def _is_thin_shim(path: Path) -> bool:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return True
    tree = _parse(path)
    allowed = (ast.Import, ast.ImportFrom, ast.Assign, ast.AnnAssign, ast.Expr)
    return all(isinstance(node, allowed) for node in tree.body)


def test_expected_domain_packages_exist() -> None:
    assert {path.name for path in (SRC_ROOT / "domains").iterdir() if path.is_dir()} == DOMAINS
    for domain in DOMAINS:
        assert (SRC_ROOT / "domains" / domain / "__init__.py").is_file()


def test_legacy_technical_packages_contain_no_business_logic() -> None:
    offenders: list[str] = []
    for package in LEGACY_PACKAGES:
        package_path = SRC_ROOT / package
        if not package_path.exists():
            continue
        for path in package_path.rglob("*.py"):
            if path.name == "__init__.py":
                continue
            if path in SHIM_ALLOWED_FILES:
                continue
            if not _is_thin_shim(path):
                offenders.append(path.relative_to(ROOT).as_posix())
    assert offenders == []


def test_root_package_contains_only_entry_shims() -> None:
    allowed = {"__init__.py", "__main__.py", "cli.py"}
    actual = {path.name for path in SRC_ROOT.glob("*.py")}
    assert actual <= allowed


def test_platform_does_not_import_domains_or_integrations_or_app() -> None:
    offenders: list[tuple[str, str]] = []
    for path in (SRC_ROOT / "platform").rglob("*.py"):
        for imported in _imports(path):
            if imported.startswith(("gmgn_twitter_intel.domains.", "gmgn_twitter_intel.integrations.", "gmgn_twitter_intel.app.")):  # noqa: E501
                offenders.append((path.relative_to(ROOT).as_posix(), imported))
    assert offenders == []


def test_cross_domain_imports_use_interfaces() -> None:
    offenders: list[tuple[str, str]] = []
    for path in (SRC_ROOT / "domains").rglob("*.py"):
        current_domain = _domain_name(path)
        for imported in _imports(path):
            prefix = "gmgn_twitter_intel.domains."
            if not imported.startswith(prefix):
                continue
            parts = imported.removeprefix(prefix).split(".")
            imported_domain = parts[0]
            if imported_domain == current_domain:
                continue
            if len(parts) >= 2 and parts[1] == "interfaces":
                continue
            offenders.append((path.relative_to(ROOT).as_posix(), imported))
    assert offenders == []


def test_repositories_and_queries_do_not_import_services_or_runtime() -> None:
    offenders: list[tuple[str, str]] = []
    for path in (SRC_ROOT / "domains").rglob("*.py"):
        rel_parts = path.relative_to(SRC_ROOT).parts
        if "repositories" not in rel_parts and "queries" not in rel_parts:
            continue
        for imported in _imports(path):
            if ".services." in imported or ".runtime." in imported or ".read_models." in imported:
                offenders.append((path.relative_to(ROOT).as_posix(), imported))
    assert offenders == []


def test_raw_sql_is_owned_by_repositories_queries_or_app_runtime() -> None:
    offenders = [
        path.relative_to(ROOT).as_posix()
        for path in _python_files()
        if "conn.execute(" in path.read_text(encoding="utf-8") and not _is_sql_allowed(path)
    ]
    assert offenders == []


def test_no_business_modules_import_old_flat_packages() -> None:
    prefixes = tuple(f"gmgn_twitter_intel.{name}." for name in LEGACY_PACKAGES)
    offenders: list[tuple[str, str]] = []
    for path in _python_files():
        if _top_package(path) in LEGACY_PACKAGES:
            continue
        for imported in _imports(path):
            if imported.startswith(prefixes):
                offenders.append((path.relative_to(ROOT).as_posix(), imported))
    assert offenders == []
