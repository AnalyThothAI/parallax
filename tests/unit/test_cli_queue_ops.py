from __future__ import annotations

import io
import json
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

from gmgn_twitter_intel.cli import main
from tests.unit.test_queue_terminal import _FakeTerminalConnection, _terminal_row


def test_queue_inspect_dispatches_through_ops_handler(monkeypatch) -> None:
    from gmgn_twitter_intel.app.surfaces.cli.commands import ops as ops_module

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
    from gmgn_twitter_intel.app.surfaces.cli.commands import ops as ops_module
    from gmgn_twitter_intel.app.surfaces.cli.commands import queue_ops

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


def test_queue_resolve_requires_execute_and_non_empty_reason(monkeypatch) -> None:
    from gmgn_twitter_intel.app.surfaces.cli.commands import ops as ops_module

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
    from gmgn_twitter_intel.app.surfaces.cli.commands import ops as ops_module

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


def test_queue_resolve_retry_rolls_back_when_transition_requeues_nothing(monkeypatch) -> None:
    from gmgn_twitter_intel.app.surfaces.cli.commands import ops as ops_module

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


def test_queue_retry_transitions_cover_phase_five_terminal_queues() -> None:
    from gmgn_twitter_intel.app.surfaces.cli.commands import queue_ops

    assert set(queue_ops.QUEUE_RETRY_TRANSITIONS) >= {
        ("resolution_refresh", "token_discovery_dirty_lookup_keys"),
        ("event_anchor_backfill", "event_anchor_backfill_jobs"),
        ("enrichment", "enrichment_jobs"),
        ("mention_semantics", "token_mention_semantics"),
        ("pulse_candidate", "pulse_agent_jobs"),
    }


def test_queue_inspect_active_uses_queue_health_adapter(monkeypatch) -> None:
    from gmgn_twitter_intel.app.surfaces.cli.commands import ops as ops_module
    from gmgn_twitter_intel.app.surfaces.cli.commands import queue_ops

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
