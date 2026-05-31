from __future__ import annotations

from parallax.domains.evidence.repositories.evidence_repository import _sanitize_postgres_value


def test_sanitize_postgres_value_removes_null_bytes_recursively():
    payload = {
        "token": "INF\x00INIT",
        "items": ["ok", "bad\x00value"],
        "nested": {"text": "\x00leading"},
    }

    assert _sanitize_postgres_value(payload) == {
        "token": "INFINIT",
        "items": ["ok", "badvalue"],
        "nested": {"text": "leading"},
    }
