from __future__ import annotations

from copy import deepcopy
from datetime import date

from gmgn_twitter_intel.domains.macro_intel.observation_identity import (
    macro_observation_fact_payload_hash,
    macro_observation_id,
)
from gmgn_twitter_intel.domains.macro_intel.services.macrodata_bundle_importer import import_macrodata_bundle
from tests.unit.domains.macro_intel.test_macrodata_bundle_importer import ENVELOPE, NOW_MS, FakeRepositorySession


def test_import_same_payload_second_time_is_noop_not_imported_change() -> None:
    repos = FakeRepositorySession()

    first = import_macrodata_bundle(deepcopy(ENVELOPE), repos=repos, now_ms=NOW_MS)
    second = import_macrodata_bundle(deepcopy(ENVELOPE), repos=repos, now_ms=NOW_MS + 60_000)

    assert first["seen_observation_count"] == 1
    assert first["inserted_observation_count"] == 1
    assert first["changed_observation_count"] == 0
    assert first["noop_observation_count"] == 0
    assert first["imported_observation_count"] == 1

    assert second["seen_observation_count"] == 1
    assert second["inserted_observation_count"] == 0
    assert second["changed_observation_count"] == 0
    assert second["noop_observation_count"] == 1
    assert second["imported_observation_count"] == 0
    assert second["changed_observations"] == []
    assert repos.macro_intel.import_runs[-1]["imported_observation_count"] == 0


def test_import_changed_payload_counts_changed_and_surfaces_dirty_concept() -> None:
    repos = FakeRepositorySession()
    changed_envelope = deepcopy(ENVELOPE)
    changed_envelope["data"]["snapshot"]["observations"][0]["value"] = 3.52

    import_macrodata_bundle(deepcopy(ENVELOPE), repos=repos, now_ms=NOW_MS)
    summary = import_macrodata_bundle(changed_envelope, repos=repos, now_ms=NOW_MS + 60_000)

    assert summary["imported_observation_count"] == 1
    assert summary["inserted_observation_count"] == 0
    assert summary["changed_observation_count"] == 1
    assert summary["noop_observation_count"] == 0
    assert summary["changed_concept_keys"] == ["liquidity:sofr"]
    assert summary["changed_observations"] == [
        {
            "observation_id": macro_observation_id(repos.macro_intel.observations[0]),
            "status": "changed",
            "concept_key": "liquidity:sofr",
            "observed_at": date(2026, 5, 19),
            "fact_payload_hash": macro_observation_fact_payload_hash(repos.macro_intel.observations[0]),
        }
    ]
