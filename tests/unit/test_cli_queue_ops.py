from __future__ import annotations

import io
import json
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

from parallax.cli import main
from tests.unit.test_queue_terminal import _FakeTerminalConnection, _terminal_row


def test_queue_inspect_dispatches_through_ops_handler(monkeypatch) -> None:
    from parallax.app.surfaces.cli.commands import ops as ops_module

    conn = _FakeTerminalConnection()
    conn.rows = [
        _terminal_row("terminal-1", worker_name="resolution_refresh", source_table="lookup", target_key="a"),
        _terminal_row("terminal-2", worker_name="pulse", source_table="lookup", target_key="b"),
    ]

    @contextmanager
    def fake_repositories(_settings: object):
        yield SimpleNamespace(signals=SimpleNamespace(conn=conn))

    monkeypatch.setattr(ops_module, "load_settings", lambda require_ws_token=False: SimpleNamespace())
    monkeypatch.setattr(ops_module, "repositories", fake_repositories)
    stdout = io.StringIO()

    code = main(
        ["ops", "queue-inspect", "--worker", "resolution_refresh", "--status", "terminal", "--limit", "5"],
        stdout=stdout,
    )

    payload = json.loads(stdout.getvalue())
    assert code == 0
    assert payload["ok"] is True
    assert payload["data"]["count"] == 1
    assert payload["data"]["items"][0]["terminal_id"] == "terminal-1"


def test_queue_inspect_passes_reason_bucket_to_terminal_inspect(monkeypatch) -> None:
    from parallax.app.surfaces.cli.commands import ops as ops_module
    from parallax.app.surfaces.cli.commands import queue_ops

    calls: list[dict[str, Any]] = []

    @contextmanager
    def fake_repositories(_settings: object):
        yield SimpleNamespace(signals=SimpleNamespace(conn=object()))

    def fake_inspect(conn: object, **kwargs: Any) -> dict[str, Any]:
        calls.append({"conn": conn, **kwargs})
        return {
            "status": "terminal",
            "reason_bucket": kwargs["reason_bucket"],
            "count": 0,
            "items": [],
        }

    monkeypatch.setattr(ops_module, "load_settings", lambda require_ws_token=False: SimpleNamespace())
    monkeypatch.setattr(ops_module, "repositories", fake_repositories)
    monkeypatch.setattr(queue_ops, "inspect_terminal_events", fake_inspect)
    stdout = io.StringIO()

    code = main(
        [
            "ops",
            "queue-inspect",
            "--worker",
            "resolution_refresh",
            "--reason-bucket",
            "llm_provider_522",
        ],
        stdout=stdout,
    )

    assert code == 0
    assert calls[0]["reason_bucket"] == "llm_provider_522"
    payload = json.loads(stdout.getvalue())
    assert payload["data"]["reason_bucket"] == "llm_provider_522"


def test_queue_inspect_rejects_zero_limit_before_terminal_sampling(monkeypatch) -> None:
    from parallax.app.surfaces.cli.commands import ops as ops_module
    from parallax.app.surfaces.cli.commands import queue_ops

    @contextmanager
    def fake_repositories(_settings: object):
        yield SimpleNamespace(signals=SimpleNamespace(conn=object()))

    def fake_inspect(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise AssertionError("terminal queue rows must not be sampled when limit is invalid")

    monkeypatch.setattr(ops_module, "load_settings", lambda require_ws_token=False: SimpleNamespace())
    monkeypatch.setattr(ops_module, "repositories", fake_repositories)
    monkeypatch.setattr(queue_ops, "inspect_terminal_events", fake_inspect)
    stdout = io.StringIO()

    code = main(
        ["ops", "queue-inspect", "--worker", "resolution_refresh", "--status", "terminal", "--limit", "0"],
        stdout=stdout,
    )

    assert code == 1
    assert json.loads(stdout.getvalue()) == {"ok": False, "error": "limit_must_be_positive"}


def test_queue_resolve_requires_execute_and_non_empty_reason(monkeypatch) -> None:
    from parallax.app.surfaces.cli.commands import ops as ops_module

    @contextmanager
    def fake_repositories(_settings: object):
        yield SimpleNamespace(signals=SimpleNamespace(conn=_FakeTerminalConnection()))

    monkeypatch.setattr(ops_module, "load_settings", lambda require_ws_token=False: SimpleNamespace())
    monkeypatch.setattr(ops_module, "repositories", fake_repositories)

    stdout = io.StringIO()
    code = main(
        [
            "ops",
            "queue-resolve",
            "--terminal-id",
            "terminal-1",
            "--action",
            "archive",
            "--reason",
            "reviewed",
        ],
        stdout=stdout,
    )
    assert code == 1
    assert json.loads(stdout.getvalue()) == {"ok": False, "error": "execute_and_reason_required"}

    stdout = io.StringIO()
    code = main(
        [
            "ops",
            "queue-resolve",
            "--terminal-id",
            "terminal-1",
            "--action",
            "archive",
            "--reason",
            "",
            "--execute",
        ],
        stdout=stdout,
    )
    assert code == 1
    assert json.loads(stdout.getvalue()) == {"ok": False, "error": "execute_and_reason_required"}


def test_queue_resolve_retry_uses_registered_transition(monkeypatch) -> None:
    from parallax.app.surfaces.cli.commands import ops as ops_module

    conn = _FakeTerminalConnection()
    conn.rows = [
        _terminal_row(
            "terminal-1",
            worker_name="resolution_refresh",
            source_table="token_discovery_dirty_lookup_keys",
            target_key="okx_dex_search:bonk",
            source_row_json={
                "provider": "okx_dex_search",
                "lookup_key": "symbol:BONK",
                "payload_hash": "",
                "latest_seen_ms": 1_700_000_000_000,
                "intent_count": 7,
            },
        )
    ]
    repos = SimpleNamespace(signals=SimpleNamespace(conn=conn), discovery=_FakeDiscoveryRetryRepository())

    @contextmanager
    def fake_repositories(_settings: object):
        yield repos

    monkeypatch.setattr(ops_module, "load_settings", lambda require_ws_token=False: SimpleNamespace())
    monkeypatch.setattr(ops_module, "repositories", fake_repositories)
    monkeypatch.setattr(ops_module, "_now_ms", lambda: 1_700_000_100_000)
    stdout = io.StringIO()

    code = main(
        [
            "ops",
            "queue-resolve",
            "--terminal-id",
            "terminal-1",
            "--action",
            "retry",
            "--reason",
            "operator checked row",
            "--execute",
        ],
        stdout=stdout,
    )

    payload = json.loads(stdout.getvalue())
    assert code == 0
    assert payload["ok"] is True
    assert payload["data"]["operator_action"] == "retry"
    assert payload["data"]["transition"] == {
        "provider": "okx_dex_search",
        "lookup_key": "symbol:BONK",
        "requeued": 1,
        "due_at_ms": 1_700_000_100_000,
        "latest_seen_at_ms": 1_700_000_000_000,
        "intent_count": 7,
    }
    assert repos.discovery.calls == [
        {
            "lookup_keys": ["symbol:BONK"],
            "reason": "terminal_retry:operator checked row",
            "now_ms": 1_700_000_100_000,
            "due_at_ms": 1_700_000_100_000,
            "latest_seen_ms": 1_700_000_000_000,
            "intent_count": 7,
            "commit": False,
        }
    ]


def test_queue_resolve_retry_requeues_token_image_source_terminal(monkeypatch) -> None:
    from parallax.app.surfaces.cli.commands import ops as ops_module

    source_row = {
        "source_url_hash": "hash-image-source",
        "source_url": "https://gmgn.ai/external-res/logo.png",
        "source_provider": "gmgn_dex_profile",
        "source_kind": "asset_profiles.logo_url",
        "target_type": "Asset",
        "target_id": "asset:sol:logo",
        "raw_ref_json": {"asset_id": "asset:sol:logo"},
        "source_watermark_ms": 1_700_000_000_000,
        "priority": 20,
        "payload_hash": "payload-image-source",
    }
    conn = _FakeTerminalConnection()
    conn.rows = [
        _terminal_row(
            "terminal-image-1",
            worker_name="token_image_mirror",
            source_table="token_image_source_dirty_targets",
            target_key="hash-image-source:Asset:asset:sol:logo",
            source_row_json=source_row,
        )
    ]
    repos = SimpleNamespace(
        signals=SimpleNamespace(conn=conn),
        token_image_source_dirty_targets=_FakeTokenImageSourceRetryRepository(),
    )

    @contextmanager
    def fake_repositories(_settings: object):
        yield repos

    monkeypatch.setattr(ops_module, "load_settings", lambda require_ws_token=False: SimpleNamespace())
    monkeypatch.setattr(ops_module, "repositories", fake_repositories)
    monkeypatch.setattr(ops_module, "_now_ms", lambda: 1_700_000_100_000)
    stdout = io.StringIO()

    code = main(
        [
            "ops",
            "queue-resolve",
            "--terminal-id",
            "terminal-image-1",
            "--action",
            "retry",
            "--reason",
            "operator checked image source",
            "--execute",
        ],
        stdout=stdout,
    )

    payload = json.loads(stdout.getvalue())
    assert code == 0
    assert payload["ok"] is True
    assert payload["data"]["operator_action"] == "retry"
    assert payload["data"]["transition"] == {
        "requeued": 1,
        "source_url": "https://gmgn.ai/external-res/logo.png",
        "target_type": "Asset",
        "target_id": "asset:sol:logo",
        "due_at_ms": 1_700_000_100_000,
    }
    assert repos.token_image_source_dirty_targets.calls == [
        {
            "targets": [{**source_row, "due_at_ms": 1_700_000_100_000}],
            "reason": "terminal_retry:operator checked image source",
            "now_ms": 1_700_000_100_000,
            "due_at_ms": 1_700_000_100_000,
            "commit": False,
        }
    ]


def test_queue_resolve_retry_requeues_token_radar_dirty_target_with_bounded_transition_payload(monkeypatch) -> None:
    from parallax.app.surfaces.cli.commands import ops as ops_module

    source_row = {
        "target_type_key": "Asset",
        "identity_id": "asset-unit",
        "payload_hash": "payload-radar-target",
        "attempt_count": 3,
    }
    conn = _FakeTerminalConnection()
    conn.rows = [
        _terminal_row(
            "terminal-radar-target-1",
            worker_name="token_radar_projection",
            source_table="token_radar_dirty_targets",
            target_key="Asset:asset-unit",
            source_row_json=source_row,
        )
    ]
    repos = SimpleNamespace(
        signals=SimpleNamespace(conn=conn),
        token_radar_dirty_targets=_FakeTokenRadarTargetRetryRepository(),
    )

    @contextmanager
    def fake_repositories(_settings: object):
        yield repos

    monkeypatch.setattr(ops_module, "load_settings", lambda require_ws_token=False: SimpleNamespace())
    monkeypatch.setattr(ops_module, "repositories", fake_repositories)
    monkeypatch.setattr(ops_module, "_now_ms", lambda: 1_700_000_100_000)
    stdout = io.StringIO()

    code = main(
        [
            "ops",
            "queue-resolve",
            "--terminal-id",
            "terminal-radar-target-1",
            "--action",
            "retry",
            "--reason",
            "operator checked radar target",
            "--execute",
        ],
        stdout=stdout,
    )

    payload = json.loads(stdout.getvalue())
    assert code == 0
    assert payload["ok"] is True
    assert payload["data"]["operator_action"] == "retry"
    assert payload["data"]["transition"] == {"requeued": 1, "due_at_ms": 1_700_000_100_000}
    assert repos.token_radar_dirty_targets.calls == [
        {
            "targets": [source_row],
            "reason": "terminal_retry:operator checked radar target",
            "now_ms": 1_700_000_100_000,
            "due_at_ms": 1_700_000_100_000,
            "commit": False,
        }
    ]


def test_queue_resolve_retry_requeues_pulse_trigger_dirty_target_with_bounded_transition_payload(monkeypatch) -> None:
    from parallax.app.surfaces.cli.commands import ops as ops_module

    source_row = {
        "target_type": "Asset",
        "target_id": "asset-unit",
        "window": "1h",
        "scope": "all",
        "payload_hash": "payload-pulse-trigger",
        "source_watermark_ms": 1_700_000_000_000,
        "attempt_count": 3,
    }
    conn = _FakeTerminalConnection()
    conn.rows = [
        _terminal_row(
            "terminal-pulse-trigger-1",
            worker_name="pulse_candidate",
            source_table="pulse_trigger_dirty_targets",
            target_key="Asset:asset-unit:1h:all",
            source_row_json=source_row,
        )
    ]
    repos = SimpleNamespace(
        signals=SimpleNamespace(conn=conn),
        pulse_trigger_dirty_targets=_FakePulseTriggerDirtyTargetRetryRepository(),
    )

    @contextmanager
    def fake_repositories(_settings: object):
        yield repos

    monkeypatch.setattr(ops_module, "load_settings", lambda require_ws_token=False: SimpleNamespace())
    monkeypatch.setattr(ops_module, "repositories", fake_repositories)
    monkeypatch.setattr(ops_module, "_now_ms", lambda: 1_700_000_100_000)
    stdout = io.StringIO()

    code = main(
        [
            "ops",
            "queue-resolve",
            "--terminal-id",
            "terminal-pulse-trigger-1",
            "--action",
            "retry",
            "--reason",
            "operator checked pulse trigger",
            "--execute",
        ],
        stdout=stdout,
    )

    payload = json.loads(stdout.getvalue())
    assert code == 0
    assert payload["ok"] is True
    assert payload["data"]["operator_action"] == "retry"
    assert payload["data"]["transition"] == {"requeued": 1, "due_at_ms": 1_700_000_100_000}
    assert repos.pulse_trigger_dirty_targets.calls == [
        {
            "targets": [{**source_row, "due_at_ms": 1_700_000_100_000}],
            "reason": "terminal_retry:operator checked pulse trigger",
            "now_ms": 1_700_000_100_000,
            "due_at_ms": 1_700_000_100_000,
            "commit": False,
        }
    ]


def test_queue_resolve_retry_requeues_narrative_admission_dirty_target(monkeypatch) -> None:
    from parallax.app.surfaces.cli.commands import ops as ops_module

    source_row = {
        "target_type": "Asset",
        "target_id": "asset-unit",
        "window": "1h",
        "scope": "all",
        "projection_version": "radar-v1",
        "schema_version": "narrative-v1",
        "payload_hash": "payload-narrative",
        "source_watermark_ms": 1_700_000_000_000,
        "attempt_count": 3,
    }
    conn = _FakeTerminalConnection()
    conn.rows = [
        _terminal_row(
            "terminal-narrative-1",
            worker_name="narrative_admission",
            source_table="narrative_admission_dirty_targets",
            target_key="Asset:asset-unit:1h:all:radar-v1:narrative-v1",
            source_row_json=source_row,
        )
    ]
    repos = SimpleNamespace(
        signals=SimpleNamespace(conn=conn),
        narrative_admission_dirty_targets=_FakeNarrativeAdmissionDirtyTargetRetryRepository(),
    )

    @contextmanager
    def fake_repositories(_settings: object):
        yield repos

    monkeypatch.setattr(ops_module, "load_settings", lambda require_ws_token=False: SimpleNamespace())
    monkeypatch.setattr(ops_module, "repositories", fake_repositories)
    monkeypatch.setattr(ops_module, "_now_ms", lambda: 1_700_000_100_000)
    stdout = io.StringIO()

    code = main(
        [
            "ops",
            "queue-resolve",
            "--terminal-id",
            "terminal-narrative-1",
            "--action",
            "retry",
            "--reason",
            "operator checked narrative target",
            "--execute",
        ],
        stdout=stdout,
    )

    payload = json.loads(stdout.getvalue())
    assert code == 0
    assert payload["ok"] is True
    assert payload["data"]["operator_action"] == "retry"
    assert payload["data"]["transition"] == {"requeued": 1, "due_at_ms": 1_700_000_100_000}
    assert repos.narrative_admission_dirty_targets.calls == [
        {
            "targets": [{**source_row, "due_at_ms": 1_700_000_100_000}],
            "reason": "terminal_retry:operator checked narrative target",
            "now_ms": 1_700_000_100_000,
            "due_at_ms": 1_700_000_100_000,
            "commit": False,
        }
    ]


def test_queue_resolve_retry_requeues_market_tick_current_dirty_target(monkeypatch) -> None:
    from parallax.app.surfaces.cli.commands import ops as ops_module

    source_row = {
        "target_type": "chain_token",
        "target_id": "solana:unit",
        "payload_hash": "payload-market-current",
        "attempt_count": 3,
    }
    conn = _FakeTerminalConnection()
    conn.rows = [
        _terminal_row(
            "terminal-market-current-1",
            worker_name="market_tick_current_projection",
            source_table="market_tick_current_dirty_targets",
            target_key="chain_token:solana:unit",
            source_row_json=source_row,
        )
    ]
    repos = SimpleNamespace(
        signals=SimpleNamespace(conn=conn),
        market_tick_current_dirty_targets=_FakeMarketTickCurrentDirtyTargetRetryRepository(),
    )

    @contextmanager
    def fake_repositories(_settings: object):
        yield repos

    monkeypatch.setattr(ops_module, "load_settings", lambda require_ws_token=False: SimpleNamespace())
    monkeypatch.setattr(ops_module, "repositories", fake_repositories)
    monkeypatch.setattr(ops_module, "_now_ms", lambda: 1_700_000_100_000)
    stdout = io.StringIO()

    code = main(
        [
            "ops",
            "queue-resolve",
            "--terminal-id",
            "terminal-market-current-1",
            "--action",
            "retry",
            "--reason",
            "operator checked market current",
            "--execute",
        ],
        stdout=stdout,
    )

    payload = json.loads(stdout.getvalue())
    assert code == 0
    assert payload["ok"] is True
    assert payload["data"]["operator_action"] == "retry"
    assert payload["data"]["transition"] == {"requeued": 1, "due_at_ms": 1_700_000_100_000}
    assert repos.market_tick_current_dirty_targets.calls == [
        {
            "targets": [source_row],
            "reason": "terminal_retry:operator checked market current",
            "now_ms": 1_700_000_100_000,
            "commit": False,
        }
    ]


def test_queue_resolve_retry_requeues_token_radar_source_dirty_event_with_bounded_transition_payload(
    monkeypatch,
) -> None:
    from parallax.app.surfaces.cli.commands import ops as ops_module

    source_row = {
        "projection_version": "token-radar-v-test",
        "source_event_id": "event-unit",
        "target_type_key": "Asset",
        "identity_id": "asset-unit",
        "payload_hash": "payload-radar-source",
        "attempt_count": 3,
    }
    conn = _FakeTerminalConnection()
    conn.rows = [
        _terminal_row(
            "terminal-radar-source-1",
            worker_name="token_radar_projection",
            source_table="token_radar_source_dirty_events",
            target_key="token-radar-v-test:event-unit:Asset:asset-unit",
            source_row_json=source_row,
        )
    ]
    repos = SimpleNamespace(
        signals=SimpleNamespace(conn=conn),
        token_radar_source_dirty_events=_FakeTokenRadarSourceRetryRepository(),
    )

    @contextmanager
    def fake_repositories(_settings: object):
        yield repos

    monkeypatch.setattr(ops_module, "load_settings", lambda require_ws_token=False: SimpleNamespace())
    monkeypatch.setattr(ops_module, "repositories", fake_repositories)
    monkeypatch.setattr(ops_module, "_now_ms", lambda: 1_700_000_100_000)
    stdout = io.StringIO()

    code = main(
        [
            "ops",
            "queue-resolve",
            "--terminal-id",
            "terminal-radar-source-1",
            "--action",
            "retry",
            "--reason",
            "operator checked radar source",
            "--execute",
        ],
        stdout=stdout,
    )

    payload = json.loads(stdout.getvalue())
    assert code == 0
    assert payload["ok"] is True
    assert payload["data"]["operator_action"] == "retry"
    assert payload["data"]["transition"] == {"requeued": 1, "due_at_ms": 1_700_000_100_000}
    assert repos.token_radar_source_dirty_events.calls == [
        {
            "events": [source_row],
            "reason": "terminal_retry:operator checked radar source",
            "now_ms": 1_700_000_100_000,
            "due_at_ms": 1_700_000_100_000,
            "commit": False,
        }
    ]


def test_queue_resolve_retry_requeues_macro_projection_concept_target(monkeypatch) -> None:
    from parallax.app.surfaces.cli.commands import ops as ops_module

    source_row = {
        "projection_name": "macro_view",
        "projection_version": "macro_regime_v4",
        "target_kind": "concept",
        "target_id": "rates:dgs10",
        "concept_key": "rates:dgs10",
        "max_observed_at": "2026-06-23",
        "payload_hash": "payload-macro-target",
        "attempt_count": 3,
    }
    conn = _FakeTerminalConnection()
    conn.rows = [
        _terminal_row(
            "terminal-macro-target-1",
            worker_name="macro_view_projection",
            source_table="macro_projection_dirty_targets",
            target_key="macro_view:macro_regime_v4:concept:rates:dgs10",
            source_row_json=source_row,
        )
    ]
    repos = SimpleNamespace(
        signals=SimpleNamespace(conn=conn),
        macro_intel=_FakeMacroProjectionRetryRepository(),
    )

    @contextmanager
    def fake_repositories(_settings: object):
        yield repos

    monkeypatch.setattr(ops_module, "load_settings", lambda require_ws_token=False: SimpleNamespace())
    monkeypatch.setattr(ops_module, "repositories", fake_repositories)
    monkeypatch.setattr(ops_module, "_now_ms", lambda: 1_700_000_100_000)
    stdout = io.StringIO()

    code = main(
        [
            "ops",
            "queue-resolve",
            "--terminal-id",
            "terminal-macro-target-1",
            "--action",
            "retry",
            "--reason",
            "operator checked macro target",
            "--execute",
        ],
        stdout=stdout,
    )

    payload = json.loads(stdout.getvalue())
    assert code == 0
    assert payload["ok"] is True
    assert payload["data"]["operator_action"] == "retry"
    assert payload["data"]["transition"] == {
        "requeued": 1,
        "projection_name": "macro_view",
        "projection_version": "macro_regime_v4",
        "target_kind": "concept",
        "due_at_ms": 1_700_000_100_000,
    }
    assert repos.macro_intel.change_calls == [
        {
            "changed_observations": [{"concept_key": "rates:dgs10", "observed_at": "2026-06-23"}],
            "projection_name": "macro_view",
            "projection_version": "macro_regime_v4",
            "now_ms": 1_700_000_100_000,
            "due_at_ms": 1_700_000_100_000,
            "reason": "terminal_retry:operator checked macro target",
            "commit": False,
        }
    ]
    assert repos.macro_intel.current_calls == []


def test_queue_resolve_retry_rolls_back_when_transition_requeues_nothing(monkeypatch) -> None:
    from parallax.app.surfaces.cli.commands import ops as ops_module

    conn = _FakeTerminalConnection()
    conn.rows = [
        _terminal_row(
            "terminal-1",
            worker_name="resolution_refresh",
            source_table="token_discovery_dirty_lookup_keys",
            target_key="okx_dex_search:bonk",
            source_row_json={
                "provider": "okx_dex_search",
                "lookup_key": "symbol:BONK",
                "payload_hash": "",
            },
        )
    ]
    repos = SimpleNamespace(signals=SimpleNamespace(conn=conn), discovery=_FakeEmptyDiscoveryRetryRepository())

    @contextmanager
    def fake_repositories(_settings: object):
        yield repos

    monkeypatch.setattr(ops_module, "load_settings", lambda require_ws_token=False: SimpleNamespace())
    monkeypatch.setattr(ops_module, "repositories", fake_repositories)
    monkeypatch.setattr(ops_module, "_now_ms", lambda: 1_700_000_100_000)
    stdout = io.StringIO()

    code = main(
        [
            "ops",
            "queue-resolve",
            "--terminal-id",
            "terminal-1",
            "--action",
            "retry",
            "--reason",
            "operator checked row",
            "--execute",
        ],
        stdout=stdout,
    )

    assert code == 1
    assert json.loads(stdout.getvalue()) == {"ok": False, "error": "discovery_lookup_retry_not_requeued"}
    assert conn.rows[0]["operator_action"] is None
    assert conn.rollbacks == 1


def test_queue_resolve_retry_requires_discovery_repository_contract(monkeypatch) -> None:
    from parallax.app.surfaces.cli.commands import ops as ops_module

    conn = _FakeTerminalConnection()
    conn.rows = [
        _terminal_row(
            "terminal-1",
            worker_name="resolution_refresh",
            source_table="token_discovery_dirty_lookup_keys",
            target_key="okx_dex_search:bonk",
            source_row_json={
                "provider": "okx_dex_search",
                "lookup_key": "symbol:BONK",
                "payload_hash": "",
            },
        )
    ]
    repos = SimpleNamespace(signals=SimpleNamespace(conn=conn))

    @contextmanager
    def fake_repositories(_settings: object):
        yield repos

    monkeypatch.setattr(ops_module, "load_settings", lambda require_ws_token=False: SimpleNamespace())
    monkeypatch.setattr(ops_module, "repositories", fake_repositories)
    monkeypatch.setattr(ops_module, "_now_ms", lambda: 1_700_000_100_000)
    stdout = io.StringIO()

    code = main(
        [
            "ops",
            "queue-resolve",
            "--terminal-id",
            "terminal-1",
            "--action",
            "retry",
            "--reason",
            "operator checked row",
            "--execute",
        ],
        stdout=stdout,
    )

    assert code == 1
    assert json.loads(stdout.getvalue()) == {"ok": False, "error": "discovery_repository_required"}
    assert conn.rows[0]["operator_action"] is None
    assert conn.rollbacks == 1


def test_queue_resolve_bucket_dry_run_reports_count_without_terminal_ids(monkeypatch) -> None:
    from parallax.app.surfaces.cli.commands import ops as ops_module

    conn = _FakeTerminalConnection()
    conn.rows = [
        _terminal_row(
            "terminal-1",
            worker_name="event_anchor_backfill",
            source_table="event_anchor_backfill_jobs",
            target_key="event-1:intent-1",
            final_reason_bucket="provider_error",
        ),
        _terminal_row(
            "terminal-2",
            worker_name="event_anchor_backfill",
            source_table="event_anchor_backfill_jobs",
            target_key="event-2:intent-2",
            final_reason_bucket="provider_error",
        ),
    ]

    @contextmanager
    def fake_repositories(_settings: object):
        yield SimpleNamespace(signals=SimpleNamespace(conn=conn))

    monkeypatch.setattr(ops_module, "load_settings", lambda require_ws_token=False: SimpleNamespace())
    monkeypatch.setattr(ops_module, "repositories", fake_repositories)
    stdout = io.StringIO()

    code = main(
        [
            "ops",
            "queue-resolve-bucket",
            "--worker",
            "event_anchor_backfill",
            "--source-table",
            "event_anchor_backfill_jobs",
            "--reason-bucket",
            "provider_error",
            "--action",
            "archive",
            "--reason",
            "operator bucket review",
            "--limit",
            "10",
            "--dry-run",
        ],
        stdout=stdout,
    )

    text = stdout.getvalue()
    payload = json.loads(text)
    assert code == 0
    assert payload["ok"] is True
    assert payload["data"] == {
        "mode": "dry_run",
        "execute": False,
        "dry_run": True,
        "worker": "event_anchor_backfill",
        "source_table": "event_anchor_backfill_jobs",
        "reason_bucket": "provider_error",
        "action": "archive",
        "limit": 10,
        "matched_count": 2,
        "resolved_count": 0,
        "error_count": 0,
        "error_counts": {},
    }
    assert "terminal-1" not in text
    assert "terminal-2" not in text
    assert [row["operator_action"] for row in conn.rows] == [None, None]


def test_queue_resolve_bucket_execute_archives_bounded_rows_without_terminal_ids(monkeypatch) -> None:
    from parallax.app.surfaces.cli.commands import ops as ops_module

    conn = _FakeTerminalConnection()
    conn.rows = [
        _terminal_row(
            "terminal-1",
            worker_name="event_anchor_backfill",
            source_table="event_anchor_backfill_jobs",
            target_key="event-1:intent-1",
            final_reason_bucket="provider_error",
        ),
        _terminal_row(
            "terminal-2",
            worker_name="event_anchor_backfill",
            source_table="event_anchor_backfill_jobs",
            target_key="event-2:intent-2",
            final_reason_bucket="provider_error",
        ),
    ]

    @contextmanager
    def fake_repositories(_settings: object):
        yield SimpleNamespace(signals=SimpleNamespace(conn=conn))

    monkeypatch.setattr(ops_module, "load_settings", lambda require_ws_token=False: SimpleNamespace())
    monkeypatch.setattr(ops_module, "repositories", fake_repositories)
    monkeypatch.setattr(ops_module, "_now_ms", lambda: 1_700_000_100_000)
    stdout = io.StringIO()

    code = main(
        [
            "ops",
            "queue-resolve-bucket",
            "--worker",
            "event_anchor_backfill",
            "--source-table",
            "event_anchor_backfill_jobs",
            "--reason-bucket",
            "provider_error",
            "--action",
            "archive",
            "--reason",
            "operator bucket review",
            "--limit",
            "10",
            "--execute",
        ],
        stdout=stdout,
    )

    text = stdout.getvalue()
    payload = json.loads(text)
    assert code == 0
    assert payload["ok"] is True
    assert payload["data"]["matched_count"] == 2
    assert payload["data"]["resolved_count"] == 2
    assert payload["data"]["error_count"] == 0
    assert "terminal-1" not in text
    assert "terminal-2" not in text
    assert [row["operator_action"] for row in conn.rows] == ["archive", "archive"]
    assert [row["operator_reason"] for row in conn.rows] == ["operator bucket review", "operator bucket review"]


def test_queue_retry_transitions_cover_phase_five_terminal_queues() -> None:
    from parallax.app.surfaces.cli.commands import queue_ops

    assert set(queue_ops.QUEUE_RETRY_TRANSITIONS) >= {
        ("resolution_refresh", "token_discovery_dirty_lookup_keys"),
        ("event_anchor_backfill", "event_anchor_backfill_jobs"),
        ("market_tick_current_projection", "market_tick_current_dirty_targets"),
        ("narrative_admission", "narrative_admission_dirty_targets"),
        ("pulse_candidate", "pulse_agent_jobs"),
        ("pulse_candidate", "pulse_trigger_dirty_targets"),
        ("token_image_mirror", "token_image_source_dirty_targets"),
        ("token_profile_current", "token_profile_current_dirty_targets"),
        ("token_radar_projection", "token_radar_dirty_targets"),
        ("token_radar_projection", "token_radar_source_dirty_events"),
        ("macro_view_projection", "macro_projection_dirty_targets"),
    }
    assert ("mention_semantics", "token_mention_semantics") not in queue_ops.QUEUE_RETRY_TRANSITIONS


def test_queue_resolve_bucket_rejects_zero_limit_before_listing_terminal_ids(monkeypatch) -> None:
    from parallax.app.surfaces.cli.commands import ops as ops_module
    from parallax.app.surfaces.cli.commands import queue_ops

    @contextmanager
    def fake_repositories(_settings: object):
        yield SimpleNamespace(signals=SimpleNamespace(conn=object()))

    def fake_list_terminal_event_ids(*args: Any, **kwargs: Any) -> list[str]:
        raise AssertionError("terminal ids must not be listed when limit is invalid")

    monkeypatch.setattr(ops_module, "load_settings", lambda require_ws_token=False: SimpleNamespace())
    monkeypatch.setattr(ops_module, "repositories", fake_repositories)
    monkeypatch.setattr(queue_ops, "list_terminal_event_ids", fake_list_terminal_event_ids)
    stdout = io.StringIO()

    code = main(
        [
            "ops",
            "queue-resolve-bucket",
            "--worker",
            "event_anchor_backfill",
            "--source-table",
            "event_anchor_backfill_jobs",
            "--reason-bucket",
            "provider_error",
            "--action",
            "archive",
            "--reason",
            "operator bucket review",
            "--limit",
            "0",
            "--dry-run",
        ],
        stdout=stdout,
    )

    assert code == 1
    assert json.loads(stdout.getvalue()) == {"ok": False, "error": "limit_must_be_positive"}


def test_queue_inspect_active_uses_queue_health_adapter(monkeypatch) -> None:
    from parallax.app.surfaces.cli.commands import ops as ops_module
    from parallax.app.surfaces.cli.commands import queue_ops

    conn = _FakeTerminalConnection()

    @contextmanager
    def fake_repositories(_settings: object):
        yield SimpleNamespace(signals=SimpleNamespace(conn=conn))

    monkeypatch.setattr(ops_module, "load_settings", lambda require_ws_token=False: SimpleNamespace())
    monkeypatch.setattr(ops_module, "repositories", fake_repositories)
    monkeypatch.setattr(queue_ops, "_now_ms", lambda: 1_700_000_100_000)
    monkeypatch.setattr(
        queue_ops,
        "worker_queue_health_tables",
        lambda: {"resolution_refresh": ("token_discovery_dirty_lookup_keys",)},
    )
    monkeypatch.setattr(
        queue_ops,
        "fetch_queue_table_health",
        lambda conn, table, *, now_ms, worker_name: {
            "table": table,
            "worker": worker_name,
            "now_ms": now_ms,
            "queue_depth": 3,
        },
    )
    stdout = io.StringIO()

    code = main(
        [
            "ops",
            "queue-inspect",
            "--worker",
            "resolution_refresh",
            "--source-table",
            "token_discovery_dirty_lookup_keys",
            "--status",
            "active",
        ],
        stdout=stdout,
    )

    payload = json.loads(stdout.getvalue())
    assert code == 0
    assert payload["data"]["status"] == "active"
    assert payload["data"]["items"] == [
        {
            "source_table": "token_discovery_dirty_lookup_keys",
            "queue_health": {
                "table": "token_discovery_dirty_lookup_keys",
                "worker": "resolution_refresh",
                "now_ms": 1_700_000_100_000,
                "queue_depth": 3,
            },
        }
    ]


def test_queue_inspect_active_rejects_zero_limit_before_queue_health_sampling(monkeypatch) -> None:
    from parallax.app.surfaces.cli.commands import ops as ops_module
    from parallax.app.surfaces.cli.commands import queue_ops

    @contextmanager
    def fake_repositories(_settings: object):
        yield SimpleNamespace(signals=SimpleNamespace(conn=object()))

    def fake_queue_health(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise AssertionError("active queue health must not be sampled when limit is invalid")

    monkeypatch.setattr(ops_module, "load_settings", lambda require_ws_token=False: SimpleNamespace())
    monkeypatch.setattr(ops_module, "repositories", fake_repositories)
    monkeypatch.setattr(
        queue_ops,
        "worker_queue_health_tables",
        lambda: {"resolution_refresh": ("token_discovery_dirty_lookup_keys",)},
    )
    monkeypatch.setattr(queue_ops, "fetch_queue_table_health", fake_queue_health)
    stdout = io.StringIO()

    code = main(
        [
            "ops",
            "queue-inspect",
            "--worker",
            "resolution_refresh",
            "--status",
            "active",
            "--limit",
            "0",
        ],
        stdout=stdout,
    )

    assert code == 1
    assert json.loads(stdout.getvalue()) == {"ok": False, "error": "limit_must_be_positive"}


class _FakeDiscoveryRetryRepository:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def enqueue_lookup_keys(self, lookup_keys, **kwargs):
        self.calls.append({"lookup_keys": list(lookup_keys), **kwargs})
        return len(lookup_keys)


class _FakeEmptyDiscoveryRetryRepository(_FakeDiscoveryRetryRepository):
    def enqueue_lookup_keys(self, lookup_keys, **kwargs):
        self.calls.append({"lookup_keys": list(lookup_keys), **kwargs})
        return 0


class _FakePulseTriggerDirtyTargetRetryRepository:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def enqueue_targets(self, targets, **kwargs):
        self.calls.append({"targets": [dict(target) for target in targets], **kwargs})
        return {"targets": len(targets)}


class _FakeNarrativeAdmissionDirtyTargetRetryRepository(_FakePulseTriggerDirtyTargetRetryRepository):
    pass


class _FakeMarketTickCurrentDirtyTargetRetryRepository:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def enqueue_targets(self, targets, **kwargs):
        self.calls.append({"targets": [dict(target) for target in targets], **kwargs})
        return len(targets)


class _FakeTokenImageSourceRetryRepository:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def enqueue_targets(self, targets, **kwargs):
        self.calls.append({"targets": [dict(target) for target in targets], **kwargs})
        return {"targets": len(targets)}


class _FakeTokenRadarTargetRetryRepository:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def enqueue_targets(self, targets, **kwargs):
        self.calls.append({"targets": [dict(target) for target in targets], **kwargs})
        return len(targets)


class _FakeTokenRadarSourceRetryRepository:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def enqueue_events(self, events, **kwargs):
        self.calls.append({"events": [dict(event) for event in events], **kwargs})
        return len(events)


class _FakeMacroProjectionRetryRepository:
    def __init__(self) -> None:
        self.current_calls: list[dict[str, Any]] = []
        self.change_calls: list[dict[str, Any]] = []

    def enqueue_macro_projection_dirty_target(self, **kwargs: Any) -> int:
        self.current_calls.append(dict(kwargs))
        return 1

    def enqueue_macro_projection_dirty_targets_for_changes(self, changed_observations, **kwargs: Any) -> int:
        self.change_calls.append(
            {"changed_observations": [dict(observation) for observation in changed_observations], **kwargs}
        )
        return len(changed_observations)
