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
