from __future__ import annotations

import ast
import inspect
import re
import textwrap
from dataclasses import replace
from pathlib import Path

import pytest

from parallax.app.runtime import worker_manifest as worker_manifest_module
from parallax.app.runtime.wake_bus import WakeBus
from parallax.app.runtime.worker_manifest import (
    WorkerKind,
    WorkerRuntimeConstraint,
    all_worker_manifests,
    worker_class_by_name,
)

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
def test_worker_manifest_exposes_owned_tables_as_source_contract() -> None:
    for manifest in all_worker_manifests():
        expected_owned_tables = tuple(
            dict.fromkeys(
                (
                    *manifest.writes_input_observations,
                    *manifest.writes_facts,
                    *manifest.writes_read_models,
                    *manifest.writes_control_plane,
                    *manifest.side_effect_ledgers,
                )
            )
        )

        assert manifest.owned_tables == expected_owned_tables
        assert set(manifest.queue_health_tables) <= set(manifest.owned_tables)


@pytest.mark.architecture
def test_worker_manifest_exposes_read_model_writer_mapping() -> None:
    expected: dict[str, str] = {}
    for manifest in all_worker_manifests():
        for table in manifest.writes_read_models:
            assert table not in expected, f"{table} has duplicate read model writers"
            expected[table] = manifest.name

    assert worker_manifest_module.read_model_writer_by_table() == expected


@pytest.mark.architecture
def test_worker_manifest_validation_rejects_duplicate_read_model_writers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifests = list(all_worker_manifests())
    first_writer = next(manifest for manifest in manifests if manifest.writes_read_models)
    duplicate_table = first_writer.writes_read_models[0]
    second_index = next(index for index, manifest in enumerate(manifests) if manifest.name != first_writer.name)
    manifests[second_index] = replace(
        manifests[second_index],
        writes_read_models=(duplicate_table,),
        current_read_model_identities=((duplicate_table, ("stable_key",)),),
    )
    monkeypatch.setattr(worker_manifest_module, "_WORKER_MANIFESTS", tuple(manifests))

    with pytest.raises(ValueError, match=f"multiple worker manifest writers: {duplicate_table}"):
        worker_manifest_module._validate_worker_manifests()


@pytest.mark.architecture
def test_worker_manifest_validation_rejects_unowned_read_model_identities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifests = list(all_worker_manifests())
    first_writer_index = next(index for index, manifest in enumerate(manifests) if manifest.writes_read_models)
    first_writer = manifests[first_writer_index]
    manifests[first_writer_index] = replace(
        first_writer,
        current_read_model_identities=(
            *first_writer.current_read_model_identities,
            ("unowned_read_model_rows", ("stable_key",)),
        ),
    )
    monkeypatch.setattr(worker_manifest_module, "_WORKER_MANIFESTS", tuple(manifests))

    with pytest.raises(ValueError, match="current read model identities declared for unowned tables"):
        worker_manifest_module._validate_worker_manifests()


@pytest.mark.architecture
def test_worker_manifest_validation_rejects_duplicate_read_model_identity_entries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifests = list(all_worker_manifests())
    first_writer_index = next(
        index for index, manifest in enumerate(manifests) if manifest.current_read_model_identities
    )
    first_writer = manifests[first_writer_index]
    duplicate_table, _identity_columns = first_writer.current_read_model_identities[0]
    manifests[first_writer_index] = replace(
        first_writer,
        current_read_model_identities=(
            *first_writer.current_read_model_identities,
            (duplicate_table, ("another_stable_key",)),
        ),
    )
    monkeypatch.setattr(worker_manifest_module, "_WORKER_MANIFESTS", tuple(manifests))

    with pytest.raises(ValueError, match="duplicate current read model identity entries"):
        worker_manifest_module._validate_worker_manifests()


@pytest.mark.architecture
def test_worker_manifest_validation_rejects_blank_read_model_identity_tables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifests = list(all_worker_manifests())
    first_writer_index = next(
        index for index, manifest in enumerate(manifests) if manifest.current_read_model_identities
    )
    first_writer = manifests[first_writer_index]
    _table_name, identity_columns = first_writer.current_read_model_identities[0]
    manifests[first_writer_index] = replace(
        first_writer,
        current_read_model_identities=(
            ("   ", identity_columns),
            *first_writer.current_read_model_identities[1:],
        ),
    )
    monkeypatch.setattr(worker_manifest_module, "_WORKER_MANIFESTS", tuple(manifests))

    with pytest.raises(ValueError, match="blank current read model identity tables"):
        worker_manifest_module._validate_worker_manifests()


@pytest.mark.architecture
def test_worker_manifest_validation_rejects_duplicate_table_declarations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifests = list(all_worker_manifests())
    first_writer_index = next(index for index, manifest in enumerate(manifests) if manifest.writes_control_plane)
    first_writer = manifests[first_writer_index]
    duplicate_table = first_writer.writes_control_plane[0]
    manifests[first_writer_index] = replace(
        first_writer,
        writes_control_plane=(*first_writer.writes_control_plane, duplicate_table),
    )
    monkeypatch.setattr(worker_manifest_module, "_WORKER_MANIFESTS", tuple(manifests))

    with pytest.raises(ValueError, match="duplicate worker manifest table declarations"):
        worker_manifest_module._validate_worker_manifests()


@pytest.mark.architecture
def test_worker_manifest_validation_rejects_blank_table_declarations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifests = list(all_worker_manifests())
    first_writer_index = next(index for index, manifest in enumerate(manifests) if manifest.writes_control_plane)
    first_writer = manifests[first_writer_index]
    manifests[first_writer_index] = replace(
        first_writer,
        writes_control_plane=(*first_writer.writes_control_plane, "   "),
    )
    monkeypatch.setattr(worker_manifest_module, "_WORKER_MANIFESTS", tuple(manifests))

    with pytest.raises(ValueError, match="blank worker manifest table declarations"):
        worker_manifest_module._validate_worker_manifests()


@pytest.mark.architecture
def test_worker_manifest_validation_rejects_dirty_consumers_without_dirty_targets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifests = list(all_worker_manifests())
    first_dirty_index = next(
        index
        for index, manifest in enumerate(manifests)
        if manifest.runtime_constraint == WorkerRuntimeConstraint.DIRTY_TARGET_CONSUMER
    )
    manifests[first_dirty_index] = replace(manifests[first_dirty_index], dirty_target_tables=())
    monkeypatch.setattr(worker_manifest_module, "_WORKER_MANIFESTS", tuple(manifests))

    with pytest.raises(ValueError, match="dirty-target consumer manifests missing dirty target tables"):
        worker_manifest_module._validate_worker_manifests()


@pytest.mark.architecture
def test_worker_manifest_validation_rejects_leased_consumers_without_queue_depth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifests = list(all_worker_manifests())
    first_leased_index = next(
        index
        for index, manifest in enumerate(manifests)
        if manifest.runtime_constraint == WorkerRuntimeConstraint.LEASED_JOB_CONSUMER
    )
    manifests[first_leased_index] = replace(manifests[first_leased_index], queue_depth_table=None)
    monkeypatch.setattr(worker_manifest_module, "_WORKER_MANIFESTS", tuple(manifests))

    with pytest.raises(ValueError, match="leased job consumer manifests missing queue depth tables"):
        worker_manifest_module._validate_worker_manifests()


@pytest.mark.architecture
def test_worker_manifest_validation_rejects_unowned_queue_depth_tables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifests = list(all_worker_manifests())
    first_queue_index = next(index for index, manifest in enumerate(manifests) if manifest.queue_depth_table)
    manifests[first_queue_index] = replace(manifests[first_queue_index], queue_depth_table="unowned_queue_jobs")
    monkeypatch.setattr(worker_manifest_module, "_WORKER_MANIFESTS", tuple(manifests))

    with pytest.raises(ValueError, match="queue depth tables missing from worker ownership"):
        worker_manifest_module._validate_worker_manifests()


@pytest.mark.architecture
def test_worker_manifest_validation_rejects_provider_schedulers_without_provider_io(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifests = list(all_worker_manifests())
    first_provider_index = next(
        index
        for index, manifest in enumerate(manifests)
        if manifest.runtime_constraint == WorkerRuntimeConstraint.BOUNDED_PROVIDER_SCHEDULER
    )
    manifests[first_provider_index] = replace(manifests[first_provider_index], uses_provider_io=False)
    monkeypatch.setattr(worker_manifest_module, "_WORKER_MANIFESTS", tuple(manifests))

    with pytest.raises(ValueError, match="bounded provider scheduler manifests missing provider IO"):
        worker_manifest_module._validate_worker_manifests()


@pytest.mark.architecture
def test_worker_manifest_validation_rejects_ledgers_on_non_side_effect_workers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifests = list(all_worker_manifests())
    first_non_side_effect_index = next(
        index
        for index, manifest in enumerate(manifests)
        if manifest.kind not in {WorkerKind.AGENT_SIDE_EFFECT, WorkerKind.NOTIFICATION_DELIVERY}
    )
    manifests[first_non_side_effect_index] = replace(
        manifests[first_non_side_effect_index],
        side_effect_ledgers=("unexpected_side_effect_ledger",),
    )
    monkeypatch.setattr(worker_manifest_module, "_WORKER_MANIFESTS", tuple(manifests))

    with pytest.raises(ValueError, match="non-side-effect worker manifests declaring side-effect ledgers"):
        worker_manifest_module._validate_worker_manifests()


@pytest.mark.architecture
def test_worker_manifest_validation_rejects_blank_wake_channels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifests = list(all_worker_manifests())
    first_waker_index = next(index for index, manifest in enumerate(manifests) if manifest.wakes_out)
    manifests[first_waker_index] = replace(
        manifests[first_waker_index],
        wakes_out=(*manifests[first_waker_index].wakes_out, "   "),
    )
    monkeypatch.setattr(worker_manifest_module, "_WORKER_MANIFESTS", tuple(manifests))

    with pytest.raises(ValueError, match="blank worker manifest wake channels"):
        worker_manifest_module._validate_worker_manifests()


@pytest.mark.architecture
def test_worker_manifest_validation_rejects_duplicate_wake_channels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifests = list(all_worker_manifests())
    first_listener_index = next(index for index, manifest in enumerate(manifests) if manifest.wakes_on)
    duplicate_channel = manifests[first_listener_index].wakes_on[0]
    manifests[first_listener_index] = replace(
        manifests[first_listener_index],
        wakes_on=(*manifests[first_listener_index].wakes_on, duplicate_channel),
    )
    monkeypatch.setattr(worker_manifest_module, "_WORKER_MANIFESTS", tuple(manifests))

    with pytest.raises(ValueError, match="duplicate worker manifest wake channels"):
        worker_manifest_module._validate_worker_manifests()


@pytest.mark.architecture
def test_worker_manifest_validation_rejects_duplicate_advisory_lock_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifests = list(all_worker_manifests())
    locked_indexes = [index for index, manifest in enumerate(manifests) if manifest.advisory_lock_key is not None]
    duplicate_lock_key = manifests[locked_indexes[0]].advisory_lock_key
    manifests[locked_indexes[1]] = replace(manifests[locked_indexes[1]], advisory_lock_key=duplicate_lock_key)
    monkeypatch.setattr(worker_manifest_module, "_WORKER_MANIFESTS", tuple(manifests))

    with pytest.raises(ValueError, match="duplicate worker manifest advisory lock keys"):
        worker_manifest_module._validate_worker_manifests()


@pytest.mark.architecture
def test_worker_manifest_validation_rejects_blank_advisory_lock_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifests = list(all_worker_manifests())
    first_locked_index = next(index for index, manifest in enumerate(manifests) if manifest.advisory_lock_key)
    manifests[first_locked_index] = replace(manifests[first_locked_index], advisory_lock_key="   ")
    monkeypatch.setattr(worker_manifest_module, "_WORKER_MANIFESTS", tuple(manifests))

    with pytest.raises(ValueError, match="blank worker manifest advisory lock keys"):
        worker_manifest_module._validate_worker_manifests()


@pytest.mark.architecture
def test_worker_manifest_validation_rejects_blank_identity_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifests = list(all_worker_manifests())
    manifests[0] = replace(manifests[0], name="   ")
    monkeypatch.setattr(worker_manifest_module, "_WORKER_MANIFESTS", tuple(manifests))

    with pytest.raises(ValueError, match="blank worker manifest identity fields"):
        worker_manifest_module._validate_worker_manifests()


@pytest.mark.architecture
def test_worker_manifest_validation_rejects_blank_idempotency_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifests = list(all_worker_manifests())
    manifests[0] = replace(manifests[0], idempotency_evidence=(*manifests[0].idempotency_evidence, "   "))
    monkeypatch.setattr(worker_manifest_module, "_WORKER_MANIFESTS", tuple(manifests))

    with pytest.raises(ValueError, match="blank worker manifest idempotency evidence"):
        worker_manifest_module._validate_worker_manifests()


@pytest.mark.architecture
def test_worker_manifest_validation_rejects_empty_input_contracts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifests = list(all_worker_manifests())
    manifests[0] = replace(manifests[0], input_contract=())
    monkeypatch.setattr(worker_manifest_module, "_WORKER_MANIFESTS", tuple(manifests))

    with pytest.raises(ValueError, match="worker manifests missing input contracts"):
        worker_manifest_module._validate_worker_manifests()


@pytest.mark.architecture
def test_worker_manifest_validation_rejects_duplicate_read_model_identity_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifests = list(all_worker_manifests())
    first_writer_index = next(
        index for index, manifest in enumerate(manifests) if manifest.current_read_model_identities
    )
    first_writer = manifests[first_writer_index]
    table_name, identity_columns = first_writer.current_read_model_identities[0]
    duplicate_column = identity_columns[0]
    manifests[first_writer_index] = replace(
        first_writer,
        current_read_model_identities=(
            (table_name, (*identity_columns, duplicate_column)),
            *first_writer.current_read_model_identities[1:],
        ),
    )
    monkeypatch.setattr(worker_manifest_module, "_WORKER_MANIFESTS", tuple(manifests))

    with pytest.raises(ValueError, match="duplicate current read model identity columns"):
        worker_manifest_module._validate_worker_manifests()


@pytest.mark.architecture
def test_worker_manifest_validation_rejects_empty_read_model_identity_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifests = list(all_worker_manifests())
    first_writer_index = next(
        index for index, manifest in enumerate(manifests) if manifest.current_read_model_identities
    )
    first_writer = manifests[first_writer_index]
    table_name, _identity_columns = first_writer.current_read_model_identities[0]
    manifests[first_writer_index] = replace(
        first_writer,
        current_read_model_identities=(
            (table_name, ()),
            *first_writer.current_read_model_identities[1:],
        ),
    )
    monkeypatch.setattr(worker_manifest_module, "_WORKER_MANIFESTS", tuple(manifests))

    with pytest.raises(ValueError, match="empty current read model identity columns"):
        worker_manifest_module._validate_worker_manifests()


@pytest.mark.architecture
def test_worker_manifest_validation_rejects_blank_read_model_identity_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifests = list(all_worker_manifests())
    first_writer_index = next(
        index for index, manifest in enumerate(manifests) if manifest.current_read_model_identities
    )
    first_writer = manifests[first_writer_index]
    table_name, identity_columns = first_writer.current_read_model_identities[0]
    manifests[first_writer_index] = replace(
        first_writer,
        current_read_model_identities=(
            (table_name, (*identity_columns, "   ")),
            *first_writer.current_read_model_identities[1:],
        ),
    )
    monkeypatch.setattr(worker_manifest_module, "_WORKER_MANIFESTS", tuple(manifests))

    with pytest.raises(ValueError, match="blank current read model identity columns"):
        worker_manifest_module._validate_worker_manifests()


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
    return {
        table: [worker_name]
        for table, worker_name in sorted(worker_manifest_module.read_model_writer_by_table().items())
    }


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
