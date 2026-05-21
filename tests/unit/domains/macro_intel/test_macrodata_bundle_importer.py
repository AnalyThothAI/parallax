from __future__ import annotations

from copy import deepcopy
from decimal import Decimal

import pytest

from gmgn_twitter_intel.domains.macro_intel.services.macrodata_bundle_importer import (
    import_macrodata_bundle,
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
            "series_key": "nyfed:SOFR",
            "observed_at": "2026-05-19",
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
    assert import_run["coverage_json"] == {"requested": 20, "available": 1}
    assert import_run["missing_series_json"] == ["fred:WALCL"]
    assert import_run["series_errors_json"] == [
        {"series_key": "fred:WALCL", "provider": "fred", "code": "missing_api_key"}
    ]
    assert import_run["reason_codes_json"] == ["missing_series", "missing_api_key"]
    assert import_run["started_at_ms"] == NOW_MS
    assert import_run["completed_at_ms"] == NOW_MS
    assert summary == {
        "bundle_name": "macro-core",
        "asof": "2026-05-21",
        "observations_count": 1,
        "imported_observation_ids": ["observation-1"],
        "run_id": import_run["run_id"],
        "status": "partial",
        "data_quality": "partial",
        "coverage": {"requested": 20, "available": 1},
        "missing_series": ["fred:WALCL"],
        "series_errors": [{"series_key": "fred:WALCL", "provider": "fred", "code": "missing_api_key"}],
        "reason_codes": ["missing_series", "missing_api_key"],
    }


def test_import_macrodata_bundle_validates_all_observations_before_writing() -> None:
    envelope = deepcopy(ENVELOPE)
    envelope["data"]["snapshot"]["observations"].append({"provider": "fred", "observed_at": "2026-05-19"})
    repos = FakeRepositorySession()

    with pytest.raises(ValueError, match="series_key"):
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


@pytest.mark.parametrize("raw_value", ["3.51", True])
def test_import_macrodata_bundle_stores_none_for_non_numeric_values(raw_value: object) -> None:
    envelope = deepcopy(ENVELOPE)
    envelope["data"]["snapshot"]["observations"][0]["value"] = raw_value
    repos = FakeRepositorySession()

    import_macrodata_bundle(envelope, repos=repos, now_ms=NOW_MS)

    assert repos.macro_intel.observations[0]["value_numeric"] is None


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
        self.macro_intel = FakeMacroIntelRepository(fail_record_run=fail_record_run)

    def unit_of_work(self):
        return FakeTransaction(self)


class FakeTransaction:
    def __init__(self, repos: FakeRepositorySession) -> None:
        self.repos = repos
        self.observations: list[dict[str, object]] = []
        self.import_runs: list[dict[str, object]] = []

    def __enter__(self):
        self.observations = list(self.repos.macro_intel.observations)
        self.import_runs = list(self.repos.macro_intel.import_runs)
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc_type is not None:
            self.repos.macro_intel.observations = self.observations
            self.repos.macro_intel.import_runs = self.import_runs
            self.repos.transaction_events.append("rollback")
        else:
            self.repos.transaction_events.append("commit")
        return False


class FakeConnection:
    def __init__(self) -> None:
        self.commits = 0

    def commit(self) -> None:
        self.commits += 1


class FakeMacroIntelRepository:
    def __init__(self, *, fail_record_run: bool = False) -> None:
        self.observations: list[dict[str, object]] = []
        self.import_runs: list[dict[str, object]] = []
        self.fail_record_run = fail_record_run

    def upsert_observation(self, observation: dict[str, object]) -> str:
        self.observations.append(observation)
        return f"observation-{len(self.observations)}"

    def record_import_run(self, import_run: dict[str, object]) -> None:
        if self.fail_record_run:
            raise RuntimeError("record_run_failed")
        self.import_runs.append(import_run)
