from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from parallax.app.runtime.worker_manifest import (
    FORBIDDEN_SERVING_IDENTITY_COLUMNS,
    WorkerKind,
    WorkerRuntimeConstraint,
    all_worker_manifests,
)
from parallax.platform.current_read_model_payload_hash import stable_current_payload_hash

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
def test_resolution_refresh_manifest_is_dirty_lookup_queue_consumer() -> None:
    manifest = {manifest.name: manifest for manifest in all_worker_manifests()}["resolution_refresh"]

    assert manifest.runtime_constraint is WorkerRuntimeConstraint.DIRTY_TARGET_CONSUMER
    assert manifest.input_contract == ("token_discovery_dirty_lookup_keys",)
    assert manifest.dirty_target_tables == ("token_discovery_dirty_lookup_keys",)
    assert manifest.queue_depth_table == "token_discovery_dirty_lookup_keys"
    assert manifest.uses_provider_io is True


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
def test_provider_io_manifest_inventory_is_explicit() -> None:
    provider_io_workers = {manifest.name for manifest in all_worker_manifests() if manifest.uses_provider_io}

    assert provider_io_workers == {
        "asset_profile_refresh",
        "cex_oi_radar_board",
        "collector",
        "event_anchor_backfill",
        "macro_sync",
        "market_tick_poll",
        "market_tick_stream",
        "news_fetch",
        "resolution_refresh",
        "token_image_mirror",
    }


@pytest.mark.architecture
@pytest.mark.parametrize(
    "payload",
    [
        123,
        [("target_id", "asset-1"), ("score", 10)],
        "legacy-payload",
    ],
    ids=["scalar", "pairs", "string"],
)
def test_stable_current_payload_hash_rejects_non_mapping_payloads(payload: object) -> None:
    with pytest.raises(ValueError, match="current payload hash payload must be mapping"):
        stable_current_payload_hash(payload)


@pytest.mark.architecture
def test_stable_current_payload_hash_rejects_non_string_payload_keys() -> None:
    with pytest.raises(ValueError, match="current payload hash payload has non-string keys"):
        stable_current_payload_hash({123: "legacy"})


@pytest.mark.architecture
def test_stable_current_payload_hash_rejects_nested_non_string_payload_keys() -> None:
    with pytest.raises(ValueError, match="current payload hash payload has non-string keys"):
        stable_current_payload_hash({"target_id": "asset-1", "factor_snapshot": {123: "legacy"}})


@pytest.mark.architecture
def test_stable_current_payload_hash_rejects_generic_isoformat_payload_values() -> None:
    class LegacyIsoformatValue:
        def isoformat(self) -> str:
            return "legacy"

        def __repr__(self) -> str:
            return "LegacyIsoformatValue()"

    with pytest.raises(ValueError, match="current payload hash payload has unsupported values"):
        stable_current_payload_hash({"target_id": "asset-1", "observed_at": LegacyIsoformatValue()})


@pytest.mark.architecture
@pytest.mark.parametrize(
    "value",
    [
        float("nan"),
        float("inf"),
        Decimal("NaN"),
        Decimal("Infinity"),
    ],
    ids=["float-nan", "float-infinity", "decimal-nan", "decimal-infinity"],
)
def test_stable_current_payload_hash_rejects_non_finite_payload_numbers(value: float | Decimal) -> None:
    with pytest.raises(ValueError, match="current payload hash payload has non-finite numbers"):
        stable_current_payload_hash({"target_id": "asset-1", "score": value})


@pytest.mark.architecture
@pytest.mark.parametrize(
    "value",
    [
        {"source-a", "source-b"},
        frozenset(("source-a", "source-b")),
    ],
    ids=["set", "frozenset"],
)
def test_stable_current_payload_hash_rejects_unordered_payload_containers(value: set[str] | frozenset[str]) -> None:
    with pytest.raises(ValueError, match="current payload hash payload has unsupported containers"):
        stable_current_payload_hash({"target_id": "asset-1", "sources": value})
