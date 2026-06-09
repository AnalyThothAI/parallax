from __future__ import annotations

from pathlib import Path

import pytest

from parallax.app.runtime.current_read_model_publisher import (
    FORBIDDEN_SERVING_IDENTITY_COLUMNS,
    CurrentReadModelPublisher,
)
from parallax.app.runtime.worker_manifest import WorkerKind, all_worker_manifests

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "src/parallax/app/runtime"


@pytest.mark.architecture
def test_workerspace_runtime_modules_are_removed() -> None:
    assert not (RUNTIME / "worker_space.py").exists()
    assert not (RUNTIME / "runtime_worker_context.py").exists()


@pytest.mark.architecture
def test_current_read_model_workers_declare_explicit_table_identities_without_fallback() -> None:
    offenders = {
        manifest.name: sorted(
            set(manifest.writes_read_models)
            - {table_name for table_name, _identity_columns in manifest.current_read_model_identities}
        )
        for manifest in all_worker_manifests()
        if manifest.writes_read_models
        and set(manifest.writes_read_models)
        - {table_name for table_name, _identity_columns in manifest.current_read_model_identities}
    }

    assert offenders == {}


@pytest.mark.architecture
def test_current_read_model_manifest_identities_do_not_use_lifecycle_columns() -> None:
    violations: list[str] = []
    for manifest in all_worker_manifests():
        for table_name, identity_columns in manifest.current_read_model_identities:
            forbidden = sorted(set(identity_columns) & FORBIDDEN_SERVING_IDENTITY_COLUMNS)
            if forbidden:
                violations.append(f"{manifest.name}:{table_name}:{forbidden}")

    assert violations == []


@pytest.mark.architecture
def test_dirty_target_workers_declare_claim_tables_and_read_model_identity() -> None:
    manifests = {manifest.name: manifest for manifest in all_worker_manifests()}

    for worker_name in (
        "macro_view_projection",
        "market_tick_current_projection",
        "token_radar_projection",
        "token_profile_current",
        "pulse_candidate",
    ):
        manifest = manifests[worker_name]
        assert manifest.kind in {WorkerKind.PROJECTION, WorkerKind.AGENT_SIDE_EFFECT}
        assert manifest.dirty_target_tables
        assert set(manifest.dirty_target_tables).issubset(set(manifest.writes_control_plane))
        if manifest.writes_read_models:
            assert manifest.current_read_model_identities

    macro = manifests["macro_view_projection"]
    assert dict(macro.current_read_model_identities) == {
        "macro_observation_series_rows": ("projection_version", "concept_key", "observed_at"),
        "macro_observation_series_publication_state": ("projection_version",),
        "macro_view_snapshots": ("projection_version",),
    }
    assert macro.uses_provider_io is False

    cex = manifests["cex_oi_radar_board"]
    assert dict(cex.current_read_model_identities)["cex_oi_radar_rows"] == (
        "board_provider",
        "board_exchange",
        "board_quote_symbol",
        "board_contract_type",
        "period",
        "target_id",
    )
    assert "symbol" not in dict(cex.current_read_model_identities)["cex_oi_radar_rows"]


@pytest.mark.architecture
def test_provider_io_manifest_workers_are_bounded_and_not_projection_claim_loaders() -> None:
    manifests = {manifest.name: manifest for manifest in all_worker_manifests()}

    for worker_name in ("collector", "market_tick_stream", "market_tick_poll", "macro_sync", "cex_oi_radar_board"):
        manifest = manifests[worker_name]
        assert manifest.uses_provider_io is True
        assert manifest.dirty_target_tables == ()

    assert manifests["news_page_projection"].uses_provider_io is False
    assert manifests["macro_view_projection"].uses_provider_io is False


@pytest.mark.architecture
def test_current_read_model_publisher_rejects_non_string_payload_hash_column() -> None:
    with pytest.raises(ValueError, match="non-string current payload hash column"):
        CurrentReadModelPublisher(identity_columns=("target_id",), payload_hash_column=123)


@pytest.mark.architecture
def test_current_read_model_publisher_rejects_blank_payload_hash_column() -> None:
    with pytest.raises(ValueError, match="blank current payload hash column"):
        CurrentReadModelPublisher(identity_columns=("target_id",), payload_hash_column="   ")


@pytest.mark.architecture
def test_current_read_model_publisher_rejects_lifecycle_payload_hash_column() -> None:
    with pytest.raises(ValueError, match="payload hash column cannot be lifecycle"):
        CurrentReadModelPublisher(identity_columns=("target_id",), payload_hash_column="computed_at_ms")


@pytest.mark.architecture
def test_current_read_model_publisher_rejects_identity_payload_hash_column() -> None:
    with pytest.raises(ValueError, match="payload hash column cannot be identity column"):
        CurrentReadModelPublisher(identity_columns=("target_id",), payload_hash_column="target_id")


@pytest.mark.architecture
def test_current_read_model_publisher_rejects_non_tuple_payload_columns() -> None:
    with pytest.raises(ValueError, match="non-tuple current payload columns"):
        CurrentReadModelPublisher(identity_columns=("target_id",), payload_columns=["target_id"])


@pytest.mark.architecture
def test_current_read_model_publisher_rejects_non_string_payload_columns() -> None:
    with pytest.raises(ValueError, match="non-string current payload columns"):
        CurrentReadModelPublisher(identity_columns=("target_id",), payload_columns=("target_id", 123))


@pytest.mark.architecture
def test_current_read_model_publisher_rejects_blank_payload_columns() -> None:
    with pytest.raises(ValueError, match="blank current payload columns"):
        CurrentReadModelPublisher(identity_columns=("target_id",), payload_columns=("target_id", "   "))


@pytest.mark.architecture
def test_current_read_model_publisher_rejects_duplicate_payload_columns() -> None:
    with pytest.raises(ValueError, match="duplicate current payload columns"):
        CurrentReadModelPublisher(identity_columns=("target_id",), payload_columns=("target_id", "score", "score"))


@pytest.mark.architecture
def test_current_read_model_publisher_rejects_payload_hash_payload_columns() -> None:
    with pytest.raises(ValueError, match="payload columns cannot include payload hash column"):
        CurrentReadModelPublisher(identity_columns=("target_id",), payload_columns=("target_id", "payload_hash"))


@pytest.mark.architecture
def test_current_read_model_publisher_rejects_lifecycle_payload_columns() -> None:
    with pytest.raises(ValueError, match="payload columns cannot include lifecycle columns"):
        CurrentReadModelPublisher(identity_columns=("target_id",), payload_columns=("target_id", "computed_at_ms"))


@pytest.mark.architecture
def test_current_read_model_publisher_rejects_missing_explicit_payload_column() -> None:
    publisher = CurrentReadModelPublisher(identity_columns=("target_id",), payload_columns=("target_id", "score"))

    with pytest.raises(KeyError, match="score"):
        publisher.row_payload_hash({"target_id": "asset-1"})


@pytest.mark.architecture
def test_current_read_model_publisher_rejects_run_generation_identity_and_skips_unchanged() -> None:
    with pytest.raises(ValueError, match="non-string stable identity columns"):
        CurrentReadModelPublisher(identity_columns=("target_id", 123))
    with pytest.raises(ValueError, match="lifecycle columns"):
        CurrentReadModelPublisher(identity_columns=("run_id", "target_id"))
    with pytest.raises(ValueError, match="lifecycle columns"):
        CurrentReadModelPublisher(identity_columns=("generation_id", "target_id"))
    with pytest.raises(ValueError, match="duplicate stable identity columns"):
        CurrentReadModelPublisher(identity_columns=("target_id", "target_id"))
    with pytest.raises(ValueError, match="blank stable identity columns"):
        CurrentReadModelPublisher(identity_columns=("target_id", "   "))

    publisher = CurrentReadModelPublisher(
        identity_columns=("target_id",),
        payload_columns=("target_id", "score"),
    )
    first = publisher.changed_rows([{"target_id": "asset-1", "score": 10}], existing_hashes={})
    existing_hashes = {("asset-1",): first[0]["payload_hash"]}
    unchanged = publisher.changed_rows([{"target_id": "asset-1", "score": 10}], existing_hashes=existing_hashes)
    changed = publisher.changed_rows([{"target_id": "asset-1", "score": 11}], existing_hashes=existing_hashes)

    assert len(first) == 1
    assert unchanged == []
    assert len(changed) == 1
