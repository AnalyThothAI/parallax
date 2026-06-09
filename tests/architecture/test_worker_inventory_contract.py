from __future__ import annotations

import ast
import inspect
import re
import textwrap
from pathlib import Path

import pytest

from parallax.app.runtime.wake_bus import WakeBus
from parallax.app.runtime.worker_manifest import all_worker_manifests, worker_class_by_name

ROOT = Path(__file__).resolve().parents[2]
DOCS_WORKERS = ROOT / "docs" / "WORKERS.md"
MANIFEST_WORKER_CLASSES = worker_class_by_name()


@pytest.mark.architecture
def test_architecture_tests_do_not_import_peer_architecture_tests_as_sources() -> None:
    violations: list[str] = []
    for path in sorted((ROOT / "tests" / "architecture").glob("test_*.py")):
        for node in ast.walk(_parse(path)):
            if not isinstance(node, ast.ImportFrom) or node.module is None:
                continue
            if node.module.startswith("tests.architecture.test_"):
                violations.append(f"{_rel(path)} imports {node.module}")

    assert violations == []


@pytest.mark.architecture
def test_worker_inventory_keys_match_runtime_registry_and_settings() -> None:
    from parallax.platform.config.settings import WorkersSettings

    inventory = _worker_inventory()
    marker_keys = _worker_inventory_marker_keys()
    table_keys = set(inventory)
    manifest_keys = set(MANIFEST_WORKER_CLASSES)
    settings_keys = set(WorkersSettings.model_fields) - {"defaults", "agent_runtime"}

    assert marker_keys == manifest_keys, _key_diff_message("worker-inventory marker", marker_keys, manifest_keys)
    assert table_keys == manifest_keys, _key_diff_message("Worker Inventory table", table_keys, manifest_keys)
    assert settings_keys == manifest_keys, _key_diff_message("WorkersSettings", settings_keys, manifest_keys)


@pytest.mark.architecture
def test_documented_wake_inputs_match_default_worker_settings() -> None:
    from parallax.platform.config.settings import WorkersSettings

    inventory = _worker_inventory()
    settings = WorkersSettings()
    mismatches: list[str] = []
    for worker_key in sorted(set(WorkersSettings.model_fields) - {"defaults", "agent_runtime"}):
        expected = set(getattr(getattr(settings, worker_key), "wakes_on", ()))
        documented = _cell_code_values(inventory[worker_key]["Wake-in"])
        missing = sorted(expected - documented)
        extra = sorted(documented - expected)
        if missing or extra:
            mismatches.append(
                f"{worker_key} Wake-in mismatch: missing={missing}, extra={extra}, "
                f"expected={sorted(expected)}, documented={sorted(documented)}"
            )

    assert mismatches == []


@pytest.mark.architecture
def test_wake_bus_notify_channels_are_documented_as_wake_outputs() -> None:
    inventory = _worker_inventory()
    documented_wake_out = {channel for row in inventory.values() for channel in _cell_code_values(row["Wake-out"])}
    notify_channels = _wake_bus_notify_channels()

    missing = sorted(notify_channels - documented_wake_out)
    assert missing == [], (
        "WakeBus notify channels missing from at least one Worker Inventory Wake-out cell: "
        f"{missing}; documented={sorted(documented_wake_out)}"
    )


@pytest.mark.architecture
def test_documented_single_writer_read_models_match_worker_manifest() -> None:
    inventory = _worker_inventory()
    expected_by_table = _manifest_read_model_writer_rows()
    documented_by_table: dict[str, list[str]] = {table: [] for table in expected_by_table}
    for worker_key, row in inventory.items():
        writes = _cell_code_values(row["Writes"])
        for table, documented_workers in documented_by_table.items():
            if table in writes:
                documented_workers.append(worker_key)

    problems: list[str] = []
    for table, documented_workers in sorted(documented_by_table.items()):
        expected_workers = expected_by_table.get(table, [])
        if documented_workers != expected_workers:
            problems.append(
                f"{table} should appear in exactly the WorkerManifest writer Writes cells; "
                f"expected={expected_workers}, documented={documented_workers}"
            )

    assert problems == []


def _manifest_read_model_writer_rows() -> dict[str, list[str]]:
    expected_by_table: dict[str, list[str]] = {}
    for manifest in all_worker_manifests():
        for table in manifest.writes_read_models:
            expected_by_table.setdefault(table, []).append(manifest.name)

    duplicate_writers = {table: sorted(workers) for table, workers in expected_by_table.items() if len(workers) > 1}
    assert duplicate_writers == {}, "WorkerManifest read models must have exactly one runtime writer"
    return {table: sorted(workers) for table, workers in expected_by_table.items()}


def _rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _worker_inventory() -> dict[str, dict[str, str]]:
    section = _section_text(DOCS_WORKERS.read_text(encoding="utf-8"), "Worker Inventory")
    rows = [line for line in section.splitlines() if line.startswith("|")]
    assert len(rows) >= 3, "docs/WORKERS.md Worker Inventory table is missing or malformed"
    headers = _split_markdown_row(rows[0])
    assert "Worker" in headers, f"Worker Inventory table headers missing Worker column: {headers}"
    inventory: dict[str, dict[str, str]] = {}
    for row in rows[2:]:
        cells = _split_markdown_row(row)
        assert len(cells) == len(headers), f"Malformed Worker Inventory row: {row}"
        item = dict(zip(headers, cells, strict=True))
        worker_key = _worker_key_from_cell(item["Worker"])
        assert worker_key not in inventory, f"Duplicate worker inventory row for {worker_key}"
        inventory[worker_key] = item
    return inventory


def _worker_inventory_marker_keys() -> set[str]:
    text = DOCS_WORKERS.read_text(encoding="utf-8")
    marker = re.search(r"<!--\s*worker-inventory-keys:\s*(.*?)\s*-->", text, re.DOTALL)
    assert marker is not None, "docs/WORKERS.md is missing <!-- worker-inventory-keys: ... --> marker"
    return {key.strip() for key in marker.group(1).replace("\n", " ").split(",") if key.strip()}


def _wake_bus_notify_channels() -> set[str]:
    channels: set[str] = set()
    for name, method in inspect.getmembers(WakeBus, predicate=inspect.isfunction):
        if not name.startswith("notify_"):
            continue
        tree = ast.parse(textwrap.dedent(inspect.getsource(method)))
        literals = [
            node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)
        ]
        assert literals, f"WakeBus.{name} does not expose a literal channel name"
        channels.add(literals[0])
    return channels


def _section_text(text: str, heading: str) -> str:
    pattern = rf"^## {re.escape(heading)}\s*$"
    match = re.search(pattern, text, re.MULTILINE)
    assert match is not None, f"docs/WORKERS.md missing ## {heading} section"
    next_heading = re.search(r"^## ", text[match.end() :], re.MULTILINE)
    end = match.end() + next_heading.start() if next_heading else len(text)
    return text[match.end() : end]


def _split_markdown_row(row: str) -> list[str]:
    return [cell.strip() for cell in row.strip().strip("|").split("|")]


def _worker_key_from_cell(cell: str) -> str:
    match = re.match(r"`([^`]+)`", cell)
    assert match is not None, f"Worker cell must start with canonical key in backticks: {cell}"
    return match.group(1)


def _cell_code_values(cell: str) -> set[str]:
    return set(re.findall(r"`([^`]+)`", cell))


def _key_diff_message(label: str, actual: set[str], expected: set[str]) -> str:
    return (
        f"{label} worker keys differ from canonical registry: "
        f"missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
    )
