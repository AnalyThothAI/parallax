from __future__ import annotations

from copy import deepcopy
from datetime import date
from decimal import Decimal

import pytest

from gmgn_twitter_intel.domains.macro_intel.observation_identity import (
    macro_observation_fact_payload_hash,
    macro_observation_id,
)
from gmgn_twitter_intel.domains.macro_intel.services.macrodata_bundle_importer import (
    import_macrodata_bundle,
    parse_macrodata_bundle,
    write_macrodata_bundle_import,
)

NOW_MS = 1_779_000_000_000

ENVELOPE = {
    "ok": True,
    "command": "bundle.macro-core",
    "data": {
        "snapshot": {
            "bundle": "macro-core",
            "asof": "2026-05-21",
            "observations": [
                {
                    "series_key": "nyfed:SOFR",
                    "provider": "nyfed",
                    "dataset": "SOFR",
                    "observed_at": "2026-05-19",
                    "value": 3.51,
                    "unit": "percent",
                    "frequency": "daily",
                    "source_ts": "2026-05-19",
                    "data_quality": "ok",
                    "provenance": [{"provider": "nyfed", "source_url": "https://markets.newyorkfed.org"}],
                }
            ],
            "coverage": {"requested": 20, "available": 1},
            "missing_series": ["fred:WALCL"],
            "series_errors": [{"series_key": "fred:WALCL", "provider": "fred", "code": "missing_api_key"}],
            "source_chain": ["nyfed"],
            "data_quality": "partial",
            "reason_codes": ["missing_series", "missing_api_key"],
        }
    },
}


def test_import_macrodata_bundle_upserts_observation_and_records_run() -> None:
    repos = FakeRepositorySession()

    summary = import_macrodata_bundle(ENVELOPE, repos=repos, now_ms=NOW_MS)

    assert repos.conn.commits == 0
    assert repos.transaction_events == ["commit"]
    assert repos.macro_intel.observations == [
        {
            "source_name": "nyfed",
            "concept_key": "liquidity:sofr",
            "series_key": "nyfed:SOFR",
            "source_priority": 100,
            "observed_at": date(2026, 5, 19),
            "value_numeric": 3.51,
            "unit": "percent",
            "frequency": "daily",
            "data_quality": "ok",
            "source_ts": "2026-05-19",
            "raw_payload": ENVELOPE["data"]["snapshot"]["observations"][0],
            "ingested_at_ms": NOW_MS,
        }
    ]
    assert len(repos.macro_intel.import_runs) == 1
    import_run = repos.macro_intel.import_runs[0]
    assert import_run["source_name"] == "macrodata-cli"
    assert import_run["bundle_name"] == "macro-core"
    assert import_run["asof_date"] == "2026-05-21"
    assert import_run["status"] == "partial"
    assert import_run["observations_count"] == 1
    assert import_run["seen_observation_count"] == 1
    assert import_run["inserted_observation_count"] == 1
    assert import_run["changed_observation_count"] == 0
    assert import_run["noop_observation_count"] == 0
    assert import_run["coverage_json"] == {"requested": 20, "available": 1}
    assert import_run["missing_series_json"] == ["fred:WALCL"]
    assert import_run["series_errors_json"] == [
        {"series_key": "fred:WALCL", "provider": "fred", "code": "missing_api_key"}
    ]
    assert import_run["reason_codes_json"] == ["missing_series", "missing_api_key"]
    assert import_run["started_at_ms"] == NOW_MS
    assert import_run["completed_at_ms"] == NOW_MS
    assert summary["bundle_name"] == "macro-core"
    assert summary["asof"] == "2026-05-21"
    assert summary["max_observed_at"] == date(2026, 5, 19)
    assert summary["observations_count"] == 1
    assert summary["seen_observation_count"] == 1
    assert summary["inserted_observation_count"] == 1
    assert summary["changed_observation_count"] == 0
    assert summary["noop_observation_count"] == 0
    assert summary["imported_observation_count"] == 1
    assert summary["imported_observation_ids"] == [macro_observation_id(repos.macro_intel.observations[0])]
    assert summary["run_id"] == import_run["run_id"]
    assert summary["import_run_id"] == import_run["run_id"]
    assert summary["status"] == "partial"
    assert summary["data_quality"] == "partial"
    assert summary["coverage"] == {"requested": 20, "available": 1}
    assert summary["missing_series"] == ["fred:WALCL"]
    assert summary["series_errors"] == [{"series_key": "fred:WALCL", "provider": "fred", "code": "missing_api_key"}]
    assert summary["reason_codes"] == ["missing_series", "missing_api_key"]
    assert summary["dirty_targets_enqueued"] == 1
    assert repos.macro_intel.enqueued_dirty_targets == [
        {
            "changed_observations": [
                {
                    "observation_id": macro_observation_id(repos.macro_intel.observations[0]),
                    "status": "inserted",
                    "concept_key": "liquidity:sofr",
                    "observed_at": date(2026, 5, 19),
                    "fact_payload_hash": macro_observation_fact_payload_hash(repos.macro_intel.observations[0]),
                }
            ],
            "projection_name": "macro_view",
            "projection_version": "macro_regime_v4",
            "now_ms": NOW_MS,
            "due_at_ms": NOW_MS,
            "reason": "macro_observations_changed",
            "commit": False,
        }
    ]


def test_import_macrodata_bundle_validates_all_observations_before_writing() -> None:
    envelope = deepcopy(ENVELOPE)
    envelope["data"]["snapshot"]["observations"].append({"provider": "fred", "observed_at": "2026-05-19"})
    repos = FakeRepositorySession()

    with pytest.raises(ValueError, match="series_key"):
        import_macrodata_bundle(envelope, repos=repos, now_ms=NOW_MS)

    assert repos.transaction_events == []
    assert repos.macro_intel.observations == []
    assert repos.macro_intel.import_runs == []


def test_parse_macrodata_bundle_validates_all_observations_before_write() -> None:
    envelope = deepcopy(ENVELOPE)
    envelope["data"]["snapshot"]["observations"].append({"provider": "fred", "observed_at": "2026-05-19"})

    with pytest.raises(ValueError, match="series_key"):
        parse_macrodata_bundle(envelope, now_ms=NOW_MS)


def test_write_macrodata_bundle_import_does_not_open_its_own_transaction() -> None:
    repos = FakeRepositorySession()
    parsed = parse_macrodata_bundle(ENVELOPE, now_ms=NOW_MS)

    with repos.unit_of_work():
        summary = write_macrodata_bundle_import(parsed, repos=repos)

    assert repos.transaction_events == ["commit"]
    assert repos.conn.commits == 0
    assert summary["max_observed_at"] == date(2026, 5, 19)
    assert summary["asof"] == "2026-05-21"
    assert summary["import_run_id"] == repos.macro_intel.import_runs[0]["run_id"]
    assert summary["imported_observation_count"] == 1
    assert summary["dirty_targets_enqueued"] == 1


def test_write_macrodata_bundle_import_requires_external_transaction() -> None:
    repos = FakeRepositorySession()
    parsed = parse_macrodata_bundle(ENVELOPE, now_ms=NOW_MS)

    with pytest.raises(RuntimeError, match="macrodata_bundle_import"):
        write_macrodata_bundle_import(parsed, repos=repos)

    assert repos.macro_intel.observations == []
    assert repos.macro_intel.import_runs == []


def test_import_macrodata_bundle_rejects_unknown_macro_core_series_before_writing() -> None:
    envelope = deepcopy(ENVELOPE)
    envelope["data"]["snapshot"]["observations"][0]["series_key"] = "fred:NOT_A_CORE_SERIES"
    repos = FakeRepositorySession()

    with pytest.raises(ValueError, match="unknown macro-core series_key"):
        import_macrodata_bundle(envelope, repos=repos, now_ms=NOW_MS)

    assert repos.transaction_events == []
    assert repos.macro_intel.observations == []
    assert repos.macro_intel.import_runs == []


def test_import_macrodata_bundle_rolls_back_observations_when_import_run_fails() -> None:
    repos = FakeRepositorySession(fail_record_run=True)

    with pytest.raises(RuntimeError, match="record_run_failed"):
        import_macrodata_bundle(ENVELOPE, repos=repos, now_ms=NOW_MS)

    assert repos.conn.commits == 0
    assert repos.transaction_events == ["rollback"]
    assert repos.macro_intel.observations == []
    assert repos.macro_intel.import_runs == []


@pytest.mark.parametrize("raw_value", ["n/a", True])
def test_import_macrodata_bundle_stores_none_for_non_numeric_values(raw_value: object) -> None:
    envelope = deepcopy(ENVELOPE)
    envelope["data"]["snapshot"]["observations"][0]["value"] = raw_value
    repos = FakeRepositorySession()

    import_macrodata_bundle(envelope, repos=repos, now_ms=NOW_MS)

    assert repos.macro_intel.observations[0]["value_numeric"] is None


def test_import_macrodata_bundle_accepts_numeric_string_values() -> None:
    envelope = deepcopy(ENVELOPE)
    envelope["data"]["snapshot"]["observations"][0]["value"] = "3.51"
    repos = FakeRepositorySession()

    import_macrodata_bundle(envelope, repos=repos, now_ms=NOW_MS)

    assert repos.macro_intel.observations[0]["value_numeric"] == pytest.approx(3.51)


def test_import_macrodata_bundle_accepts_decimal_values() -> None:
    envelope = deepcopy(ENVELOPE)
    envelope["data"]["snapshot"]["observations"][0]["value"] = Decimal("3.51")
    repos = FakeRepositorySession()

    import_macrodata_bundle(envelope, repos=repos, now_ms=NOW_MS)

    assert repos.macro_intel.observations[0]["value_numeric"] == Decimal("3.51")


def test_import_macrodata_bundle_rejects_invalid_envelope() -> None:
    with pytest.raises(ValueError, match=r"data\.snapshot"):
        import_macrodata_bundle({"ok": True, "data": {}}, repos=FakeRepositorySession(), now_ms=NOW_MS)


class FakeRepositorySession:
    def __init__(self, *, fail_record_run: bool = False) -> None:
        self.conn = FakeConnection()
        self.transaction_events: list[str] = []
        self.transaction_depth = 0
        self.macro_intel = FakeMacroIntelRepository(fail_record_run=fail_record_run)

    def unit_of_work(self):
        return FakeTransaction(self)

    def require_transaction(self, *, operation: str) -> None:
        if self.transaction_depth <= 0:
            raise RuntimeError(f"{operation}:transaction_required")


class FakeTransaction:
    def __init__(self, repos: FakeRepositorySession) -> None:
        self.repos = repos
        self.observations: list[dict[str, object]] = []
        self.import_runs: list[dict[str, object]] = []
        self.enqueued_dirty_targets: list[dict[str, object]] = []

    def __enter__(self):
        self.repos.transaction_depth += 1
        self.observations = list(self.repos.macro_intel.observations)
        self.observation_index = dict(self.repos.macro_intel._observation_index)
        self.import_runs = list(self.repos.macro_intel.import_runs)
        self.enqueued_dirty_targets = list(self.repos.macro_intel.enqueued_dirty_targets)
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc_type is not None:
            self.repos.macro_intel.observations = self.observations
            self.repos.macro_intel._observation_index = self.observation_index
            self.repos.macro_intel.import_runs = self.import_runs
            self.repos.macro_intel.enqueued_dirty_targets = self.enqueued_dirty_targets
            self.repos.transaction_events.append("rollback")
        else:
            self.repos.transaction_events.append("commit")
        self.repos.transaction_depth -= 1
        return False


class FakeConnection:
    def __init__(self) -> None:
        self.commits = 0

    def commit(self) -> None:
        self.commits += 1


class FakeMacroIntelRepository:
    def __init__(self, *, fail_record_run: bool = False) -> None:
        self.observations: list[dict[str, object]] = []
        self._observation_index: dict[str, int] = {}
        self.import_runs: list[dict[str, object]] = []
        self.enqueued_dirty_targets: list[dict[str, object]] = []
        self.fail_record_run = fail_record_run

    def upsert_observation(self, observation: dict[str, object]) -> dict[str, object]:
        observation_id = macro_observation_id(observation)
        fact_payload_hash = macro_observation_fact_payload_hash(observation)
        existing_index = self._observation_index.get(observation_id)
        if existing_index is None:
            self._observation_index[observation_id] = len(self.observations)
            self.observations.append(dict(observation))
            status = "inserted"
        else:
            existing = self.observations[existing_index]
            existing_hash = macro_observation_fact_payload_hash(existing)
            if existing_hash == fact_payload_hash:
                status = "noop"
            else:
                self.observations[existing_index] = dict(observation)
                status = "changed"
        return {
            "observation_id": observation_id,
            "status": status,
            "concept_key": str(observation["concept_key"]),
            "observed_at": observation["observed_at"],
            "fact_payload_hash": fact_payload_hash,
        }

    def record_import_run(self, import_run: dict[str, object]) -> None:
        if self.fail_record_run:
            raise RuntimeError("record_run_failed")
        self.import_runs.append(import_run)

    def enqueue_macro_projection_dirty_targets_for_changes(self, **kwargs: object) -> int:
        self.enqueued_dirty_targets.append(dict(kwargs))
        return 1
