from __future__ import annotations

import io
import json
from contextlib import contextmanager
from types import TracebackType

from gmgn_twitter_intel.app.surfaces.cli.parser import build_parser
from gmgn_twitter_intel.cli import main
from gmgn_twitter_intel.domains.macro_intel._constants import MACRO_CORE_SERIES

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
                    "observed_at": "2026-05-19",
                    "value": 3.51,
                    "unit": "percent",
                    "frequency": "daily",
                    "source_ts": "2026-05-19",
                    "data_quality": "ok",
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


def test_macro_import_bundle_parser_accepts_file() -> None:
    args = build_parser().parse_args(["macro", "import-bundle", "--file", "bundle.json"])

    assert args.command == "macro"
    assert args.macro_command == "import-bundle"
    assert args.file == "bundle.json"
    assert args.stdin is False


def test_macro_import_bundle_parser_accepts_stdin() -> None:
    args = build_parser().parse_args(["macro", "import-bundle", "--stdin"])

    assert args.command == "macro"
    assert args.macro_command == "import-bundle"
    assert args.file is None
    assert args.stdin is True


def test_macro_project_once_and_status_parsers() -> None:
    project = build_parser().parse_args(["macro", "project-once"])
    status = build_parser().parse_args(["macro", "status"])

    assert project.command == "macro"
    assert project.macro_command == "project-once"
    assert status.command == "macro"
    assert status.macro_command == "status"


def test_macro_import_bundle_from_file_dispatches_to_importer(tmp_path, monkeypatch) -> None:
    from gmgn_twitter_intel.app.surfaces.cli.commands import macro as macro_module

    bundle_path = tmp_path / "macro-core.json"
    bundle_path.write_text(json.dumps(ENVELOPE), encoding="utf-8")
    repo = FakeMacroIntelRepository()
    _patch_macro_dependencies(monkeypatch, macro_module, repo)
    stdout = io.StringIO()

    code = main(["macro", "import-bundle", "--file", str(bundle_path)], stdout=stdout)

    payload = json.loads(stdout.getvalue())
    assert code == 0
    assert payload["ok"] is True
    assert payload["data"]["bundle_name"] == "macro-core"
    assert payload["data"]["observations_count"] == 1
    assert payload["data"]["run_id"] == repo.import_runs[0]["run_id"]
    assert repo.observations[0]["series_key"] == "nyfed:SOFR"
    assert repo.conn.commits == 0
    assert repo.transaction_events == ["commit"]


def test_macro_import_bundle_from_stdin_dispatches_to_importer(monkeypatch) -> None:
    from gmgn_twitter_intel.app.surfaces.cli.commands import macro as macro_module

    repo = FakeMacroIntelRepository()
    _patch_macro_dependencies(monkeypatch, macro_module, repo)
    monkeypatch.setattr(macro_module.sys, "stdin", io.StringIO(json.dumps(ENVELOPE)))
    stdout = io.StringIO()

    code = main(["macro", "import-bundle", "--stdin"], stdout=stdout)

    payload = json.loads(stdout.getvalue())
    assert code == 0
    assert payload["ok"] is True
    assert payload["data"]["coverage"] == {"requested": 20, "available": 1}
    assert repo.observations[0]["raw_payload"]["series_key"] == "nyfed:SOFR"
    assert repo.transaction_events == ["commit"]


def test_macro_import_bundle_requires_exactly_one_input(monkeypatch) -> None:
    from gmgn_twitter_intel.app.surfaces.cli.commands import macro as macro_module

    repo = FakeMacroIntelRepository()
    _patch_macro_dependencies(monkeypatch, macro_module, repo)
    stdout = io.StringIO()

    code = main(["macro", "import-bundle"], stdout=stdout)

    assert code == 2
    assert json.loads(stdout.getvalue()) == {"ok": False, "error": "macro_import_bundle_requires_file_or_stdin"}
    assert repo.observations == []


def test_macro_import_bundle_reports_repository_failure_without_secret(tmp_path, monkeypatch) -> None:
    from gmgn_twitter_intel.app.surfaces.cli.commands import macro as macro_module

    bundle_path = tmp_path / "macro-core.json"
    bundle_path.write_text(json.dumps(ENVELOPE), encoding="utf-8")
    repo = FakeMacroIntelRepository(fail_record_run=True)
    _patch_macro_dependencies(monkeypatch, macro_module, repo)
    stdout = io.StringIO()

    code = main(["macro", "import-bundle", "--file", str(bundle_path)], stdout=stdout)

    output = stdout.getvalue()
    assert code == 1
    assert "secret" not in output
    assert json.loads(output) == {
        "ok": False,
        "error": "macro_import_bundle_failed",
        "detail": "RuntimeError",
    }
    assert repo.observations == []


def test_macro_project_once_builds_snapshot_from_bounded_history(monkeypatch) -> None:
    from gmgn_twitter_intel.app.surfaces.cli.commands import macro as macro_module

    repo = FakeMacroIntelRepository(
        observations=[
            {
                "source_name": "nyfed",
                "series_key": "nyfed:SOFR",
                "observed_at": "2026-05-19",
                "value_numeric": 3.51,
                "unit": "percent",
                "frequency": "daily",
                "data_quality": "ok",
                "source_ts": "2026-05-19",
            }
        ]
    )
    _patch_macro_dependencies(monkeypatch, macro_module, repo)
    stdout = io.StringIO()

    code = main(["macro", "project-once"], stdout=stdout)

    payload = json.loads(stdout.getvalue())
    assert code == 0
    assert payload["ok"] is True
    assert payload["data"]["projection_version"] == "macro_regime_v2"
    assert payload["data"]["status"] == "partial"
    assert payload["data"]["snapshot_id"] == "macro-view:macro_regime_v2:1779000000000"
    assert repo.observations_for_series_calls == [
        {
            "series_keys": MACRO_CORE_SERIES,
            "lookback_days": 1095,
            "limit_per_series": 800,
        }
    ]
    assert repo.latest_observation_limits == []
    assert len(repo.snapshots) == 1


def test_macro_project_once_reports_repository_failure_without_secret(monkeypatch) -> None:
    from gmgn_twitter_intel.app.surfaces.cli.commands import macro as macro_module

    repo = FakeMacroIntelRepository(fail_observations_for_series=True)
    _patch_macro_dependencies(monkeypatch, macro_module, repo)
    stdout = io.StringIO()

    code = main(["macro", "project-once"], stdout=stdout)

    output = stdout.getvalue()
    assert code == 1
    assert "secret" not in output
    assert json.loads(output) == {
        "ok": False,
        "error": "macro_project_once_failed",
        "detail": "RuntimeError",
    }
    assert repo.snapshots == []


def test_macro_status_reports_repository_counts(monkeypatch) -> None:
    from gmgn_twitter_intel.app.surfaces.cli.commands import macro as macro_module

    repo = FakeMacroIntelRepository()
    repo.latest_import = {"run_id": "run-1", "bundle_name": "macro-core", "completed_at_ms": NOW_MS}
    repo.latest = {"snapshot_id": "snapshot-1", "status": "partial", "computed_at_ms": NOW_MS}
    _patch_macro_dependencies(monkeypatch, macro_module, repo)
    stdout = io.StringIO()

    code = main(["macro", "status"], stdout=stdout)

    assert code == 0
    assert json.loads(stdout.getvalue()) == {
        "ok": True,
        "data": {
            "migration_ready": True,
            "observations_count": 0,
            "series_count": 0,
            "latest_import_run": {"run_id": "run-1", "bundle_name": "macro-core", "completed_at_ms": NOW_MS},
            "latest_snapshot": {"snapshot_id": "snapshot-1", "status": "partial", "computed_at_ms": NOW_MS},
        },
    }


def _patch_macro_dependencies(monkeypatch, macro_module, repo: FakeMacroIntelRepository) -> None:
    @contextmanager
    def fake_repositories(_settings: object):
        yield FakeRepositorySession(repo)

    monkeypatch.setattr(macro_module, "load_settings", lambda require_ws_token=False: object())
    monkeypatch.setattr(macro_module, "repositories", fake_repositories)
    monkeypatch.setattr(macro_module, "_now_ms", lambda: NOW_MS)


class FakeConnection:
    def __init__(self) -> None:
        self.commits = 0

    def commit(self) -> None:
        self.commits += 1


class FakeMacroIntelRepository:
    def __init__(
        self,
        *,
        observations: list[dict[str, object]] | None = None,
        fail_record_run: bool = False,
        fail_latest_observations: bool = False,
        fail_observations_for_series: bool = False,
    ) -> None:
        self.conn = FakeConnection()
        self.source_observations = observations or []
        self.observations: list[dict[str, object]] = []
        self.import_runs: list[dict[str, object]] = []
        self.snapshots: list[dict[str, object]] = []
        self.latest_observation_limits: list[int] = []
        self.observations_for_series_calls: list[dict[str, object]] = []
        self.latest_import: dict[str, object] | None = None
        self.latest: dict[str, object] | None = None
        self.fail_record_run = fail_record_run
        self.fail_latest_observations = fail_latest_observations
        self.fail_observations_for_series = fail_observations_for_series
        self.transaction_events: list[str] = []

    def upsert_observation(self, observation: dict[str, object]) -> str:
        self.observations.append(observation)
        return f"observation-{len(self.observations)}"

    def record_import_run(self, import_run: dict[str, object]) -> None:
        if self.fail_record_run:
            raise RuntimeError("postgres://user:secret@db record failed")
        self.import_runs.append(import_run)

    def latest_observations(self, *, limit: int) -> list[dict[str, object]]:
        if self.fail_latest_observations:
            raise RuntimeError("postgres://user:secret@db latest failed")
        self.latest_observation_limits.append(limit)
        return self.source_observations

    def observations_for_series(
        self,
        *,
        series_keys: tuple[str, ...],
        lookback_days: int,
        limit_per_series: int,
    ) -> list[dict[str, object]]:
        if self.fail_observations_for_series:
            raise RuntimeError("postgres://user:secret@db history failed")
        self.observations_for_series_calls.append(
            {
                "series_keys": series_keys,
                "lookback_days": lookback_days,
                "limit_per_series": limit_per_series,
            }
        )
        return self.source_observations

    def insert_snapshot(self, snapshot: dict[str, object]) -> None:
        self.snapshots.append(snapshot)

    def observations_count(self) -> int:
        return len(self.observations)

    def series_count(self) -> int:
        return len({observation["series_key"] for observation in self.observations})

    def latest_import_run(self) -> dict[str, object] | None:
        return self.latest_import

    def latest_snapshot(self) -> dict[str, object] | None:
        return self.latest


class FakeRepositorySession:
    def __init__(self, macro_intel: FakeMacroIntelRepository) -> None:
        self.macro_intel = macro_intel
        self.conn = macro_intel.conn

    def unit_of_work(self):
        return FakeTransaction(self.macro_intel)


class FakeTransaction:
    def __init__(self, macro_intel: FakeMacroIntelRepository) -> None:
        self.macro_intel = macro_intel
        self.observations: list[dict[str, object]] = []
        self.import_runs: list[dict[str, object]] = []

    def __enter__(self):
        self.observations = list(self.macro_intel.observations)
        self.import_runs = list(self.macro_intel.import_runs)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        if exc_type is not None:
            self.macro_intel.observations = self.observations
            self.macro_intel.import_runs = self.import_runs
            self.macro_intel.transaction_events.append("rollback")
        else:
            self.macro_intel.transaction_events.append("commit")
        return False
