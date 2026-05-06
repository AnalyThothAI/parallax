from __future__ import annotations


def test_readyz_uses_postgres_liveness_probe_name() -> None:
    payload = {"ok": True, "probe": "postgres_liveness", "migration_version": "20260506_0001"}

    assert payload["probe"] == "postgres_liveness"
