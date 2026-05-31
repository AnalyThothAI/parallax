from __future__ import annotations

import pytest

from parallax.app.runtime.current_read_model_publisher import CurrentReadModelPublisher
from parallax.app.runtime.worker_manifest import all_worker_manifests
from parallax.app.runtime.worker_space import (
    ClaimDiscipline,
    WorkerSpace,
    WorkerSpaceViolation,
    contract_from_manifest,
    contracts_from_manifests,
)


@pytest.mark.architecture
def test_every_worker_manifest_maps_to_valid_workerspace_contract() -> None:
    contracts = contracts_from_manifests(all_worker_manifests())
    errors = [error for contract in contracts for error in contract.validate()]

    assert errors == []


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
def test_dirty_target_workers_are_claim_first_read_model_publishers() -> None:
    contracts = {contract.worker_name: contract for contract in contracts_from_manifests(all_worker_manifests())}

    for worker_name in (
        "macro_view_projection",
        "market_tick_current_projection",
        "token_radar_projection",
        "token_profile_current",
        "pulse_candidate",
    ):
        contract = contracts[worker_name]
        assert contract.claim.discipline is ClaimDiscipline.DIRTY_TARGET
        assert contract.claim.required_before_payload_load is True
        assert contract.claim.tables

    macro = contracts["macro_view_projection"]
    assert macro.current_read_model is not None
    assert macro.current_read_model.zero_write_when_unchanged is True
    assert dict(macro.current_read_model.table_identities) == {
        "macro_observation_series_rows": ("projection_version", "concept_key", "observed_at"),
        "macro_observation_series_publication_state": ("projection_version",),
        "macro_view_snapshots": ("projection_version",),
    }
    assert macro.provider_io.allowed is False

    cex = contracts["cex_oi_radar_board"]
    assert cex.current_read_model is not None
    assert dict(cex.current_read_model.table_identities)["cex_oi_radar_rows"] == (
        "board_provider",
        "board_exchange",
        "board_quote_symbol",
        "board_contract_type",
        "period",
        "target_id",
    )
    assert "symbol" not in dict(cex.current_read_model.table_identities)["cex_oi_radar_rows"]


@pytest.mark.architecture
def test_scheduled_provider_workers_keep_provider_io_outside_db_transactions() -> None:
    contracts = {contract.worker_name: contract for contract in contracts_from_manifests(all_worker_manifests())}

    for worker_name in ("collector", "market_tick_stream", "market_tick_poll", "macro_sync", "cex_oi_radar_board"):
        contract = contracts[worker_name]
        assert contract.provider_io.allowed is True
        assert contract.provider_io.forbid_inside_db_transaction is True
        assert contract.provider_io.requires_bounded_batch is True


@pytest.mark.architecture
def test_projection_dirty_target_names_do_not_imply_provider_io() -> None:
    contracts = {contract.worker_name: contract for contract in contracts_from_manifests(all_worker_manifests())}

    assert contracts["news_page_projection"].provider_io.allowed is False
    assert contracts["macro_view_projection"].provider_io.allowed is False


@pytest.mark.architecture
def test_workerspace_runtime_guards_provider_io_and_claim_order() -> None:
    cex_manifest = next(item for item in all_worker_manifests() if item.name == "cex_oi_radar_board")
    cex_contract = contract_from_manifest(cex_manifest)
    cex_space = WorkerSpace(cex_contract)
    with (
        pytest.raises(WorkerSpaceViolation, match="provider IO inside DB transaction"),
        cex_space.db_transaction(),
        cex_space.provider_io(),
    ):
        pass

    macro_contract = contract_from_manifest(
        next(item for item in all_worker_manifests() if item.name == "macro_view_projection")
    )
    macro_space = WorkerSpace(macro_contract)
    with pytest.raises(WorkerSpaceViolation, match="payload loaded before claim"):
        macro_space.require_claim_before_payload_load()
    macro_space.mark_claimed(count=1)
    macro_space.require_claim_before_payload_load()


@pytest.mark.architecture
def test_current_read_model_publisher_rejects_run_generation_identity_and_skips_unchanged() -> None:
    with pytest.raises(ValueError, match="lifecycle columns"):
        CurrentReadModelPublisher(identity_columns=("run_id", "target_id"))
    with pytest.raises(ValueError, match="lifecycle columns"):
        CurrentReadModelPublisher(identity_columns=("generation_id", "target_id"))

    publisher = CurrentReadModelPublisher(
        identity_columns=("target_id",),
        payload_columns=("target_id", "score"),
    )
    row = {"target_id": "token:1", "score": 10, "computed_at_ms": 1000}
    row_hash = publisher.row_payload_hash(row)

    assert publisher.changed_rows([row], existing_hashes={("token:1",): row_hash}) == []
    changed_row = {**row, "score": 11}
    assert publisher.changed_rows([changed_row], existing_hashes={("token:1",): row_hash}) == [
        {**changed_row, "payload_hash": publisher.row_payload_hash(changed_row)}
    ]
