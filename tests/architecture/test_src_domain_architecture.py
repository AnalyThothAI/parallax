from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

from gmgn_twitter_intel.domains.pulse_lab.types.agent_decision import contains_trading_execution_instruction

ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = ROOT / "src" / "gmgn_twitter_intel"

DOMAINS = {
    "ingestion",
    "evidence",
    "asset_market",
    "token_intel",
    "narrative_intel",
    "news_intel",
    "social_enrichment",
    "notifications",
    "pulse_lab",
    "watchlist_intel",
    "account_quality",
}
PENDING_AGENT_A_DOMAINS = {"narrative_intel"}

ALLOWED_ROOTS = {"app", "domains", "integrations", "platform"}
PROVIDER_DOMAINS = {
    "ingestion",
    "asset_market",
    "narrative_intel",
    "news_intel",
    "social_enrichment",
    "pulse_lab",
    "watchlist_intel",
}
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
REPOSITORY_UPWARD_IMPORT_ALLOWLIST = {
    (
        SRC_ROOT / "domains/narrative_intel/repositories/narrative_repository.py",
        "gmgn_twitter_intel.domains.narrative_intel.services.fingerprints",
    ),
}
PROVIDER_WIRING_DIR = SRC_ROOT / "app" / "runtime" / "provider_wiring"
PROVIDER_WIRING_FACADE = SRC_ROOT / "app" / "runtime" / "providers_wiring.py"
OPENAI_AGENTS_DIR = SRC_ROOT / "integrations" / "openai_agents"
PROVIDER_WIRING_FACADE_ALLOWED_IMPORTS = {
    "gmgn_twitter_intel.app.runtime.provider_wiring",
    "gmgn_twitter_intel.app.runtime.provider_wiring.types",
}
PROVIDER_WIRING_FACADE_PUBLIC_EXPORTS = {
    "AssetMarketProviders",
    "IngestionProviders",
    "MarketlaneProviders",
    "NarrativeIntelProviders",
    "NewsIntelProviders",
    "PulseLabProviders",
    "SocialEnrichmentProviders",
    "UpstreamClientFactory",
    "WatchlistIntelProviders",
    "WiredProviders",
    "wire_asset_market_providers",
    "wire_providers",
}
PROVIDER_WIRING_FAMILY_PREFIX = "gmgn_twitter_intel.app.runtime.provider_wiring."
OPERATOR_CLI_PROVIDER_FAMILY_IMPORTS = {
    (
        SRC_ROOT / "app" / "surfaces" / "cli" / "commands" / "ops.py",
        "gmgn_twitter_intel.app.runtime.provider_wiring.okx",
    ),
}
FACADE_CONCRETE_EXPORTS = {
    "BinanceWeb3DexProfileProvider",
    "FallbackDexQuoteProvider",
    "GmgnDexMarketProvider",
    "OkxCexMarketProvider",
    "OkxDexDiscoveryProvider",
    "OkxDexQuoteProvider",
    "OkxDexWebSocketMarketProviderAdapter",
    "OkxProviderBundle",
    "OpenAINarrativeIntelProvider",
    "OpenAIPulseDecisionProvider",
    "openai_narrative_intel_provider",
    "okx_chain_index",
    "okx_chain_indexes_to_chain_ids",
    "okx_index_to_chain_id",
}
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


def _imported_names(path: Path) -> list[tuple[str, str, int]]:
    names: list[tuple[str, str, int]] = []
    for node in ast.walk(_parse(path)):
        if not isinstance(node, ast.ImportFrom) or node.module is None:
            continue
        if not node.module.startswith("gmgn_twitter_intel."):
            continue
        names.extend((node.module, alias.name, node.lineno) for alias in node.names)
    return names


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


def _all_import_records(path: Path) -> list[tuple[str, int]]:
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
    return records


def _all_exports(path: Path) -> set[str]:
    for node in _parse(path).body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets):
            continue
        if not isinstance(node.value, ast.List):
            continue
        exports: set[str] = set()
        for item in node.value.elts:
            if isinstance(item, ast.Constant) and isinstance(item.value, str):
                exports.add(item.value)
        return exports
    return set()


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
    actual = {path.name for path in (SRC_ROOT / "domains").iterdir() if path.is_dir() and path.name != "__pycache__"}
    expected_missing = DOMAINS - actual - PENDING_AGENT_A_DOMAINS
    unexpected = actual - DOMAINS
    _assert_no_offenders(
        sorted(expected_missing | unexpected),
        invariant="expected domain packages",
        reason="Domain package names are the source package map used by docs, tests, and agent routing.",
        fix="Add the missing domain package or update DOMAINS only when the architecture document changes.",
    )
    for domain in sorted(DOMAINS & actual):
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
            if imported.startswith(
                ("gmgn_twitter_intel.domains.", "gmgn_twitter_intel.integrations.", "gmgn_twitter_intel.app.")
            ):
                offenders.append((path.relative_to(ROOT).as_posix(), imported))  # noqa: PERF401 -- nested-loop append keeps failure construction readable
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
                if (path, imported) in REPOSITORY_UPWARD_IMPORT_ALLOWLIST:
                    continue
                offenders.append((path.relative_to(ROOT).as_posix(), imported))
    _assert_no_offenders(
        offenders,
        invariant="repositories and queries do not import upward layers",
        reason="Repository/query code owns persistence and must not depend on services, runtime, or read models.",
        fix="Move the shared value into types/interfaces or invert the call so upper layers call repositories.",
    )


def test_pulse_lab_services_do_not_import_runtime_worker_modules() -> None:
    service_root = SRC_ROOT / "domains" / "pulse_lab" / "services"
    runtime_prefix = "gmgn_twitter_intel.domains.pulse_lab.runtime."
    offenders = [
        (path.relative_to(ROOT).as_posix(), imported)
        for path in service_root.rglob("*.py")
        for imported in _imports(path)
        if imported.startswith(runtime_prefix)
    ]
    _assert_no_offenders(
        offenders,
        invariant="pulse_lab services do not depend on runtime workers",
        reason="Use-case services may be called by workers, but importing workers would recreate orchestration cycles.",
        fix="Move shared domain types into domains/pulse_lab/types or a focused service module.",
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
                offenders.append((path.relative_to(ROOT).as_posix(), imported))  # noqa: PERF401 -- nested-loop append; comprehension would harm readability
    _assert_no_offenders(
        offenders,
        invariant="business modules do not import old flat packages",
        reason="Old flat package imports bypass the domain package map and can reintroduce pre-restructure coupling.",
        fix="Import from the current app/domains/integrations/platform path instead.",
    )


def test_provider_modules_exist_only_for_allowlisted_domains() -> None:
    provider_domains = {path.parent.name for path in (SRC_ROOT / "domains").glob("*/providers.py") if path.is_file()}
    expected_provider_domains = {
        domain
        for domain in PROVIDER_DOMAINS
        if domain not in PENDING_AGENT_A_DOMAINS or (SRC_ROOT / "domains" / domain).is_dir()
    }
    offenders = [
        f"missing providers.py for domains/{domain}" for domain in sorted(expected_provider_domains - provider_domains)
    ]
    offenders.extend(
        f"unexpected providers.py in domains/{domain}" for domain in sorted(provider_domains - PROVIDER_DOMAINS)
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
    offenders: list[str] = []
    if not PROVIDER_WIRING_FACADE.is_file():
        offenders.append(f"{PROVIDER_WIRING_FACADE.relative_to(ROOT).as_posix()} missing")
    if not PROVIDER_WIRING_DIR.is_dir():
        offenders.append(f"{PROVIDER_WIRING_DIR.relative_to(ROOT).as_posix()} missing")
    facade_integration_imports = [
        f"{PROVIDER_WIRING_FACADE.relative_to(ROOT).as_posix()}:{lineno} imports {imported}"
        for imported, lineno in _import_records(PROVIDER_WIRING_FACADE)
        if imported.startswith("gmgn_twitter_intel.integrations.")
    ]
    offenders.extend(facade_integration_imports)
    for path in _python_files():
        imports = [imported for imported, _lineno in _import_records(path)]
        imports_integrations = any(imported.startswith("gmgn_twitter_intel.integrations.") for imported in imports)
        imports_domain_providers = any(
            imported.startswith("gmgn_twitter_intel.domains.") and ".providers" in imported for imported in imports
        )
        allowed_adapter_protocol_import = (
            OPENAI_AGENTS_DIR in path.parents and "gmgn_twitter_intel.domains.pulse_lab.providers" in imports
        )
        if (
            imports_integrations
            and imports_domain_providers
            and PROVIDER_WIRING_DIR not in path.parents
            and not allowed_adapter_protocol_import
        ):
            offenders.append(path.relative_to(ROOT).as_posix())
    _assert_no_offenders(
        offenders,
        invariant="provider_wiring package is the only service-process integration/provider join point",
        reason=(
            "Any other file that sees both concrete integrations and domain Provider contracts can become a "
            "second composition root. providers_wiring.py is a facade and must not import concrete integrations."
        ),
        fix=(
            "Move the join into app/runtime/provider_wiring/** and keep app/runtime/providers_wiring.py to "
            "facade exports only; CLI ops are intentionally outside this service-runtime rule."
        ),
    )


def test_providers_wiring_facade_is_lazy_and_type_only() -> None:
    offenders: list[str] = []
    for imported, lineno in _import_records(PROVIDER_WIRING_FACADE):
        if imported not in PROVIDER_WIRING_FACADE_ALLOWED_IMPORTS:
            offenders.append(f"{PROVIDER_WIRING_FACADE.relative_to(ROOT).as_posix()}:{lineno} imports {imported}")
    exports = _all_exports(PROVIDER_WIRING_FACADE)
    unexpected_exports = exports - PROVIDER_WIRING_FACADE_PUBLIC_EXPORTS
    missing_exports = PROVIDER_WIRING_FACADE_PUBLIC_EXPORTS - exports
    offenders.extend(f"unexpected facade export {name}" for name in sorted(unexpected_exports))
    offenders.extend(f"missing facade export {name}" for name in sorted(missing_exports))
    _assert_no_offenders(
        offenders,
        invariant="providers_wiring.py is a lazy public facade over provider_wiring package roots and types",
        reason=(
            "Importing the facade must not load concrete provider families or encourage monkeypatching concrete "
            "adapters through the facade."
        ),
        fix=(
            "Import only wire_providers/wire_asset_market_providers from app.runtime.provider_wiring and aggregate "
            "types from app.runtime.provider_wiring.types; concrete adapters belong in their family modules."
        ),
    )


def test_domains_and_surfaces_do_not_import_provider_family_modules_or_facade_concretes() -> None:
    offenders: list[str] = []
    scan_roots = (SRC_ROOT / "domains", SRC_ROOT / "app" / "surfaces")
    for root in scan_roots:
        for path in root.rglob("*.py"):
            for imported, lineno in _import_records(path):
                if imported.startswith(PROVIDER_WIRING_FAMILY_PREFIX):
                    if (path, imported) in OPERATOR_CLI_PROVIDER_FAMILY_IMPORTS:
                        continue
                    offenders.append(f"{path.relative_to(ROOT).as_posix()}:{lineno} imports {imported}")
            for module, name, lineno in _imported_names(path):
                if module == "gmgn_twitter_intel.app.runtime.providers_wiring" and name in FACADE_CONCRETE_EXPORTS:
                    offenders.append(f"{path.relative_to(ROOT).as_posix()}:{lineno} imports facade concrete {name}")
    _assert_no_offenders(
        offenders,
        invariant="domains and surfaces do not bypass provider family ownership",
        reason=(
            "Domains should consume aggregate provider types only, while surfaces should not reach concrete runtime "
            "provider wiring except explicit operator-only CLI commands."
        ),
        fix=(
            "Import concrete provider helpers from their app/runtime/provider_wiring/<family>.py owner only for an "
            "allowlisted operator CLI path; otherwise import aggregate types from providers_wiring.py."
        ),
    )


def test_importing_providers_wiring_facade_does_not_load_concrete_integrations() -> None:
    script = """
import importlib
import sys

before = set(sys.modules)
importlib.import_module("gmgn_twitter_intel.app.runtime.providers_wiring")
loaded = sorted(
    name for name in set(sys.modules) - before
    if name.startswith("gmgn_twitter_intel.integrations.")
)
if loaded:
    raise SystemExit("\\n".join(loaded))
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    _assert_no_offenders(
        [line for line in result.stderr.splitlines() + result.stdout.splitlines() if line.strip()],
        invariant="providers_wiring facade import does not load concrete integrations",
        reason="The facade should be cheap and side-effect-light; concrete integrations load only via family modules.",
        fix="Remove eager concrete family imports from app/runtime/providers_wiring.py.",
    )
    assert result.returncode == 0


def test_pulse_agent_route_policy_stays_in_domain() -> None:
    path = SRC_ROOT / "domains" / "pulse_lab" / "services" / "agent_routing.py"
    offenders = [
        f"{path.relative_to(ROOT).as_posix()}:{lineno} imports {imported}"
        for imported, lineno in _all_import_records(path)
        if imported.startswith("agents") or imported.startswith("gmgn_twitter_intel.integrations.")
    ]
    _assert_no_offenders(
        offenders,
        invariant="pulse agent route policy stays in the domain",
        reason="Route/completeness policy is product behavior; importing OpenAI or an agent framework hides it.",
        fix="Move integration-specific code into integrations/openai_agents or app/runtime/providers_wiring.py.",
    )


def test_pulse_lab_domain_does_not_import_openai_sdk_primitives() -> None:
    offenders: list[str] = []
    forbidden_prefixes = ("agents", "openai")
    for path in (SRC_ROOT / "domains" / "pulse_lab").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        for imported, lineno in _all_import_records(path):
            if imported.startswith(forbidden_prefixes):
                offenders.append(f"{path.relative_to(ROOT).as_posix()}:{lineno} imports {imported}")
    _assert_no_offenders(
        offenders,
        invariant="pulse_lab domain stays independent of OpenAI SDK primitives",
        reason=(
            "Pulse domain services own prompts, tool query behavior, validation, and audit assembly; "
            "SDK classes such as agents.Agent/Runner and openai clients belong in integrations/openai_agents."
        ),
        fix="Move SDK imports to integrations/openai_agents and inject domain provider protocols or services instead.",
    )


def test_openai_agent_integrations_do_not_import_repositories() -> None:
    offenders: list[str] = []
    for path in (SRC_ROOT / "integrations" / "openai_agents").rglob("*.py"):
        for imported, lineno in _import_records(path):
            if ".repositories" in imported:
                offenders.append(f"{path.relative_to(ROOT).as_posix()}:{lineno} imports {imported}")
    _assert_no_offenders(
        offenders,
        invariant="OpenAI agent integrations do not import repositories",
        reason="The adapter may run stages, but persistence belongs to domain repositories and workers.",
        fix="Return typed values from the adapter and let the owning domain runtime persist them.",
    )


def test_openai_agent_integrations_do_not_import_pulse_queries_or_services() -> None:
    offenders: list[str] = []
    forbidden = (
        "gmgn_twitter_intel.domains.pulse_lab.queries",
        "gmgn_twitter_intel.domains.pulse_lab.services",
    )
    for path in (SRC_ROOT / "integrations" / "openai_agents").rglob("*.py"):
        for imported, lineno in _import_records(path):
            if imported.startswith(forbidden):
                offenders.append(f"{path.relative_to(ROOT).as_posix()}:{lineno} imports {imported}")
    _assert_no_offenders(
        offenders,
        invariant="OpenAI agent integrations depend only on Pulse provider protocols and types",
        reason="Pulse tool queries, prompts, evidence validation, and audit assembly are domain behavior.",
        fix="Inject pulse_lab service runtimes from app/runtime/provider_wiring/openai.py instead.",
    )


def test_pulse_prompts_do_not_contain_execution_language() -> None:
    """Pulse prompts live under per-stage markdown files in
    ``domains/pulse_lab/prompts/{evidence_debate,decision_maker}.md``.

    Those markdown prompts deliberately enumerate every forbidden
    execution term inside an explicit anti-injection / "do not produce"
    section so the LLM knows what to refuse — that enumeration itself
    triggers ``contains_trading_execution_instruction`` and is the only
    expected source of matches. Scan each prompt with those guidance
    sections stripped; any remaining match indicates a real prompt drift.

    Lines stripped from the scan:

    - Lines containing an explicit forbidden marker (``禁止``, ``不允许``,
      ``绝对禁止``, ``forbidden``, ``do not``, ``✗``, ``错误``).
    - Lines under a ``## Forbidden`` / ``## 禁止`` heading until the next
      ``##`` heading.
    """

    forbidden_markers = ("禁止", "不允许", "forbidden", "do not", "✗", "错误", "must not")
    prompts_dir = SRC_ROOT / "domains" / "pulse_lab" / "prompts"
    offenders: list[str] = []
    for prompt_path in sorted(prompts_dir.glob("*.md")):
        text = prompt_path.read_text(encoding="utf-8")
        scrubbed_lines: list[str] = []
        in_forbidden_block = False
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("##"):
                heading_lower = stripped.lower()
                in_forbidden_block = (
                    "forbidden" in heading_lower
                    or "禁止" in stripped
                    or "anti-injection" in heading_lower
                    or "anti injection" in heading_lower
                )
                # Heading line itself never carries the offending example text.
                continue
            if in_forbidden_block:
                continue
            lowered = line.lower()
            if any(marker in lowered or marker in line for marker in forbidden_markers):
                continue
            scrubbed_lines.append(line)
        scrubbed = "\n".join(scrubbed_lines)
        if contains_trading_execution_instruction(scrubbed):
            offenders.append(prompt_path.relative_to(ROOT).as_posix())
    _assert_no_offenders(
        offenders,
        invariant="Pulse prompts avoid trading execution language outside explicit forbidden-word guidance",
        reason="Signal Pulse is research and monitoring only; prompts must not ask for orders or position advice.",
        fix="Rewrite prompts to discuss observation, confidence, invalidation, and residual risk only.",
    )
