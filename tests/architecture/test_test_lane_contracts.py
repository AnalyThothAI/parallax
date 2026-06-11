"""Architecture guards for test lane contracts."""

from __future__ import annotations

import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TESTS_ROOT = REPO_ROOT / "tests"
PYPROJECT = REPO_ROOT / "pyproject.toml"

ALLOWED_SKIP_PATHS = {
    Path("tests/integration/conftest.py"),
    Path("tests/e2e/conftest.py"),
    Path("tests/golden/conftest.py"),
    Path("tests/postgres_test_utils.py"),
    Path("tests/contract/test_provider_drift_live.py"),
}

BUSINESS_TEST_DIRS = ("unit", "integration", "contract", "e2e", "golden")
ENV_PREFIX = "GMGN_"
PYTEST_PREFIX = "pytest"
FAKE_PREFIX = "Fake"
PROD_POSTGRES_DSN_ENV = ENV_PREFIX + "PROD_POSTGRES_DSN"
TEST_POSTGRES_DSN_ENV = ENV_PREFIX + "TEST_POSTGRES_DSN"
PYTEST_MARK_SKIP = "@" + PYTEST_PREFIX + ".mark.skip"
PYTEST_SKIP_CALL = PYTEST_PREFIX + ".skip("
FAKE_RUNTIME_NAME = FAKE_PREFIX + "Runtime"
FAKE_REPOSITORY_NAME = FAKE_PREFIX + "Repository"
WITHOUT_POSTGRES_NAME = "without" + "_postgres"


def _relative(path: Path) -> Path:
    return path.relative_to(REPO_ROOT)


def _python_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(path for path in root.rglob("*.py") if "__pycache__" not in path.parts and path.is_file())


def _line_hits(path: Path, forbidden_terms: tuple[str, ...]) -> list[str]:
    hits: list[str] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        hits.extend(f"{_relative(path)}:{line_number}: {term}" for term in forbidden_terms if term in line)
    return hits


def test_no_root_pytest_files() -> None:
    root_pytest_files = sorted(_relative(path) for path in TESTS_ROOT.glob("test_*.py") if path.is_file())

    assert root_pytest_files == [], f"root pytest files must move into a lane: {root_pytest_files}"


def test_unit_tests_do_not_reference_live_dsns() -> None:
    forbidden_terms = (
        PROD_POSTGRES_DSN_ENV,
        TEST_POSTGRES_DSN_ENV,
        "connect_postgres_test",
    )
    hits = [hit for path in _python_files(TESTS_ROOT / "unit") for hit in _line_hits(path, forbidden_terms)]

    assert hits == [], "unit tests must not reference live PostgreSQL DSNs:\n" + "\n".join(hits)


def test_business_skips_are_not_left_in_place() -> None:
    forbidden_terms = (PYTEST_MARK_SKIP, PYTEST_SKIP_CALL)
    business_paths = [path for lane in BUSINESS_TEST_DIRS for path in _python_files(TESTS_ROOT / lane)]
    business_paths.extend(sorted(path for path in TESTS_ROOT.glob("test_*.py") if path.is_file()))

    hits = [
        hit
        for path in business_paths
        if _relative(path) not in ALLOWED_SKIP_PATHS
        for hit in _line_hits(path, forbidden_terms)
    ]

    assert hits == [], "business tests must not keep long-lived skips:\n" + "\n".join(hits)


def test_architecture_tests_do_not_skip_contracts() -> None:
    forbidden_terms = (PYTEST_MARK_SKIP, PYTEST_SKIP_CALL)
    architecture_paths = _python_files(TESTS_ROOT / "architecture")
    hits = [hit for path in architecture_paths for hit in _line_hits(path, forbidden_terms)]

    assert hits == [], "architecture harness contracts must fail closed instead of skipping:\n" + "\n".join(hits)


def test_pytest_empty_parameter_sets_fail_at_collect() -> None:
    config = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))

    assert config["tool"]["pytest"]["ini_options"]["empty_parameter_set_mark"] == "fail_at_collect"


def test_coverage_report_does_not_hide_empty_source_files() -> None:
    config = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))

    assert config["tool"]["coverage"]["report"].get("skip_empty") is False


def test_integration_tests_do_not_use_fake_runtime_repositories() -> None:
    forbidden_terms = (FAKE_RUNTIME_NAME, FAKE_REPOSITORY_NAME, WITHOUT_POSTGRES_NAME)
    hits = [hit for path in _python_files(TESTS_ROOT / "integration") for hit in _line_hits(path, forbidden_terms)]

    assert hits == [], "integration tests must use real runtime repositories:\n" + "\n".join(hits)


def test_architecture_tests_declare_harness_taxonomy() -> None:
    testing_doc = (REPO_ROOT / "docs" / "TESTING.md").read_text(encoding="utf-8")
    architecture_tests = sorted(
        path.relative_to(REPO_ROOT).as_posix() for path in (TESTS_ROOT / "architecture").glob("test_*.py")
    )
    documented_tests = sorted(
        line.split("|", 2)[1].strip().strip("`")
        for line in testing_doc.splitlines()
        if line.startswith("| `tests/architecture/test_")
    )

    for required_heading in (
        "## Harness Test Taxonomy",
        "Permanent invariant",
        "Migration tripwire",
        "Behavior contract",
        "Generated hygiene",
        "Expiry condition",
        "Replacement behavior test",
    ):
        assert required_heading in testing_doc

    assert documented_tests == architecture_tests
