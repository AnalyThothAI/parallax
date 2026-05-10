from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
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
PROVIDER_DOMAINS = {"ingestion", "asset_market", "social_enrichment", "pulse_lab"}
LEGACY_PACKAGES = {"collector", "pipeline", "retrieval", "storage", "market"}
SQL_ALLOWED_PARTS = {
    "repositories",
    "queries",
    "platform/db",
    "app/runtime",
}
DOMAIN_CROSS_CUTTING_PREFIXES = (
    "gmgn_twitter_intel.integrations.",
    "gmgn_twitter_intel.platform.db.",
    "gmgn_twitter_intel.platform.paths.",
)
SERVICE_RUNTIME_PARTS = {"services", "scoring", "runtime"}
SHIM_ALLOWED_FILES = {
    SRC_ROOT / "cli.py",
    SRC_ROOT / "__main__.py",
}


def _python_files() -> list[Path]:
    return [
        path
        for path in SRC_ROOT.rglob("*.py")
        if "__pycache__" not in path.parts and "platform/db/alembic/versions" not in path.as_posix()
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


def _import_records(path: Path) -> list[tuple[str, int]]:
    records: list[tuple[str, int]] = []
    module = _module(path)
    package_parts = module.split(".")[:-1]
    for node in ast.walk(_parse(path)):
        if isinstance(node, ast.Import):
            records.extend((alias.name, node.lineno) for alias in node.names)
        if isinstance(node, ast.ImportFrom):
            if node.module is None:
                continue
            if node.level:
                base = package_parts[: max(0, len(package_parts) - node.level + 1)]
                imported = ".".join([*base, node.module])
            else:
                imported = node.module
            records.append((imported, node.lineno))
    return [(imported, lineno) for imported, lineno in records if imported.startswith("gmgn_twitter_intel.")]


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


def _assert_no_offenders(offenders, *, invariant: str, reason: str, fix: str) -> None:
    if not offenders:
        return
    lines = [
        "违规:",
        *[f"- {item}" for item in offenders],
        f"原因: {reason}",
        f"修复: {fix}",
    ]
    assert offenders == [], "\n".join(lines) + f"\nInvariant: {invariant}"


def test_expected_domain_packages_exist() -> None:
    actual = {
        path.name for path in (SRC_ROOT / "domains").iterdir() if path.is_dir() and path.name != "__pycache__"
    }
    _assert_no_offenders(
        sorted(actual ^ DOMAINS),
        invariant="expected domain packages",
        reason="Domain package names are the source package map used by docs, tests, and agent routing.",
        fix="Add the missing domain package or update DOMAINS only when the architecture document changes.",
    )
    for domain in DOMAINS:
        _assert_no_offenders(
            [] if (SRC_ROOT / "domains" / domain / "__init__.py").is_file() else [f"domains/{domain}/__init__.py"],
            invariant="domain package init files",
            reason="Every domain directory must be an explicit Python package for import-boundary tests.",
            fix="Create the missing __init__.py file in the listed domain package.",
        )


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
    _assert_no_offenders(
        offenders,
        invariant="legacy technical packages contain no business logic",
        reason="Old flat packages must not regain runtime behavior after the domain package restructure.",
        fix="Move the code into app/domains/integrations/platform or reduce the file to a thin import shim.",
    )


def test_root_package_contains_only_entry_shims() -> None:
    allowed = {"__init__.py", "__main__.py", "cli.py"}
    actual = {path.name for path in SRC_ROOT.glob("*.py")}
    _assert_no_offenders(
        sorted(actual - allowed),
        invariant="root package only contains entry shims",
        reason="Business code at package root bypasses the app/domains/integrations/platform ownership model.",
        fix="Move each listed file into the owning root package and leave only cli.py or __main__.py shims.",
    )


def test_platform_does_not_import_domains_or_integrations_or_app() -> None:
    offenders: list[tuple[str, str]] = []
    for path in (SRC_ROOT / "platform").rglob("*.py"):
        for imported in _imports(path):
            if imported.startswith(("gmgn_twitter_intel.domains.", "gmgn_twitter_intel.integrations.", "gmgn_twitter_intel.app.")):  # noqa: E501
                offenders.append((path.relative_to(ROOT).as_posix(), imported))
    _assert_no_offenders(
        offenders,
        invariant="platform does not import app, domains, or integrations",
        reason="Platform is infrastructure; importing product or adapter code creates an inverted dependency.",
        fix="Move product decisions out of platform, or pass primitives into platform code from app/runtime.",
    )


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
    _assert_no_offenders(
        offenders,
        invariant="cross-domain imports use interfaces.py",
        reason="Direct cross-domain imports couple domains to each other's internals and defeat bounded contexts.",
        fix="Export the needed symbol from the target domain interfaces.py, then import that interface instead.",
    )


def test_repositories_and_queries_do_not_import_services_or_runtime() -> None:
    offenders: list[tuple[str, str]] = []
    for path in (SRC_ROOT / "domains").rglob("*.py"):
        rel_parts = path.relative_to(SRC_ROOT).parts
        if "repositories" not in rel_parts and "queries" not in rel_parts:
            continue
        for imported in _imports(path):
            if ".services." in imported or ".runtime." in imported or ".read_models." in imported:
                offenders.append((path.relative_to(ROOT).as_posix(), imported))
    _assert_no_offenders(
        offenders,
        invariant="repositories and queries do not import upward layers",
        reason="Repository/query code owns persistence and must not depend on services, runtime, or read models.",
        fix="Move the shared value into types/interfaces or invert the call so upper layers call repositories.",
    )


def test_raw_sql_is_owned_by_repositories_queries_or_app_runtime() -> None:
    offenders = [
        path.relative_to(ROOT).as_posix()
        for path in _python_files()
        if "conn.execute(" in path.read_text(encoding="utf-8") and not _is_sql_allowed(path)
    ]
    _assert_no_offenders(
        offenders,
        invariant="raw SQL is owned by repositories, queries, platform db, or app runtime health checks",
        reason="SQL outside persistence boundaries hides data contracts inside business and surface code.",
        fix="Move the SQL into a repository/query module and call that module from the higher layer.",
    )


def test_no_business_modules_import_old_flat_packages() -> None:
    prefixes = tuple(f"gmgn_twitter_intel.{name}." for name in LEGACY_PACKAGES)
    offenders: list[tuple[str, str]] = []
    for path in _python_files():
        if _top_package(path) in LEGACY_PACKAGES:
            continue
        for imported in _imports(path):
            if imported.startswith(prefixes):
                offenders.append((path.relative_to(ROOT).as_posix(), imported))
    _assert_no_offenders(
        offenders,
        invariant="business modules do not import old flat packages",
        reason="Old flat package imports bypass the domain package map and can reintroduce pre-restructure coupling.",
        fix="Import from the current app/domains/integrations/platform path instead.",
    )


def test_provider_modules_exist_only_for_allowlisted_domains() -> None:
    provider_domains = {
        path.parent.name
        for path in (SRC_ROOT / "domains").glob("*/providers.py")
        if path.is_file()
    }
    offenders = [
        f"missing providers.py for domains/{domain}"
        for domain in sorted(PROVIDER_DOMAINS - provider_domains)
    ]
    offenders.extend(
        f"unexpected providers.py in domains/{domain}"
        for domain in sorted(provider_domains - PROVIDER_DOMAINS)
    )
    _assert_no_offenders(
        offenders,
        invariant="provider modules exist only where a domain has real cross-cutting inbound needs",
        reason=(
            "Empty provider modules become boilerplate, while missing provider modules push Protocols into runtime "
            "or integrations."
        ),
        fix="Create providers.py only for the allowlisted domain, or remove the empty/unapproved provider module.",
    )


def test_provider_modules_remain_pure_protocol_boundaries() -> None:
    offenders: list[str] = []
    for path in (SRC_ROOT / "domains").glob("*/providers.py"):
        for imported, lineno in _import_records(path):
            if imported.startswith(DOMAIN_CROSS_CUTTING_PREFIXES):
                offenders.append(f"{path.relative_to(ROOT).as_posix()}:{lineno} imports {imported}")
    _assert_no_offenders(
        offenders,
        invariant="provider modules are pure domain Protocol boundaries",
        reason=(
            "A provider Protocol that imports a concrete integration or DB client leaks the implementation back "
            "into the domain."
        ),
        fix=(
            "Move concrete imports into app/runtime/providers_wiring.py and keep providers.py to Protocols and "
            "value objects."
        ),
    )


def test_domain_services_scoring_and_runtime_do_not_import_cross_cutting_implementations() -> None:
    offenders: list[str] = []
    for path in (SRC_ROOT / "domains").rglob("*.py"):
        rel_parts = path.relative_to(SRC_ROOT).parts
        if not SERVICE_RUNTIME_PARTS.intersection(rel_parts):
            continue
        for imported, lineno in _import_records(path):
            if imported.startswith(DOMAIN_CROSS_CUTTING_PREFIXES):
                offenders.append(f"{path.relative_to(ROOT).as_posix()}:{lineno} imports {imported}")
    _assert_no_offenders(
        offenders,
        invariant="domain service/runtime layers consume providers or unit-of-work abstractions",
        reason=(
            "Direct imports of integrations, platform.db, or platform.paths make business layers depend on "
            "infrastructure."
        ),
        fix=(
            "Move integration use to app/runtime/providers_wiring.py, or expose transaction scope through a "
            "repository/session Unit of Work."
        ),
    )


def test_app_runtime_app_does_not_import_integrations_or_domain_providers() -> None:
    path = SRC_ROOT / "app" / "runtime" / "app.py"
    offenders = [
        f"{path.relative_to(ROOT).as_posix()}:{lineno} imports {imported}"
        for imported, lineno in _import_records(path)
        if imported.startswith("gmgn_twitter_intel.integrations.")
        or (imported.startswith("gmgn_twitter_intel.domains.") and ".providers" in imported)
    ]
    _assert_no_offenders(
        offenders,
        invariant="app runtime app delegates provider construction to providers_wiring.py",
        reason=(
            "app.py should orchestrate the process; concrete integrations and domain provider imports belong in "
            "the dedicated wiring module."
        ),
        fix=(
            "Move integration construction into app/runtime/providers_wiring.py and import only the wired provider "
            "aggregate in app.py."
        ),
    )


def test_service_provider_wiring_is_the_only_integration_provider_join_point() -> None:
    wiring_path = SRC_ROOT / "app" / "runtime" / "providers_wiring.py"
    offenders: list[str] = []
    if not wiring_path.is_file():
        offenders.append(f"{wiring_path.relative_to(ROOT).as_posix()} missing")
    for path in _python_files():
        imports = [imported for imported, _lineno in _import_records(path)]
        imports_integrations = any(imported.startswith("gmgn_twitter_intel.integrations.") for imported in imports)
        imports_domain_providers = any(
            imported.startswith("gmgn_twitter_intel.domains.") and ".providers" in imported for imported in imports
        )
        if imports_integrations and imports_domain_providers and path != wiring_path:
            offenders.append(path.relative_to(ROOT).as_posix())
    _assert_no_offenders(
        offenders,
        invariant="providers_wiring.py is the only service-process integration/provider join point",
        reason=(
            "Any other file that sees both concrete integrations and domain Provider contracts can become a "
            "second composition root."
        ),
        fix=(
            "Move the join into app/runtime/providers_wiring.py; CLI ops are intentionally outside this "
            "service-runtime rule."
        ),
    )
