from __future__ import annotations

from psycopg import conninfo

from gmgn_twitter_intel.platform.db import postgres_client
from gmgn_twitter_intel.platform.db.postgres_client import (
    create_pool,
    local_docker_host_dsn,
    postgres_health_check,
    with_password_from_file,
)


class FakeCursor:
    def __init__(self) -> None:
        self.last_sql = ""

    def execute(self, sql, params=None):
        self.last_sql = str(sql)
        return self

    def fetchone(self):
        if "alembic_version" in self.last_sql:
            return {"version_num": "20260506_0003"}
        return {"ok": 1}


class FakeConn:
    def execute(self, sql, params=None):
        return FakeCursor().execute(sql, params)


def test_with_password_from_file_replaces_password(tmp_path):
    password_file = tmp_path / "pg_password"
    password_file.write_text("secret-pass\n", encoding="utf-8")

    dsn = with_password_from_file(
        "postgresql://gmgn_app:old-pass@postgres:5432/gmgn_twitter_intel",
        password_file,
    )

    assert dsn.startswith("postgresql://")
    assert "secret-pass" in dsn
    assert "old-pass" not in dsn


def test_with_password_from_file_injects_password_into_passwordless_dsn(tmp_path):
    password_file = tmp_path / "pg_password"
    password_file.write_text("secret-pass\n", encoding="utf-8")

    dsn = with_password_from_file(
        "postgresql://gmgn_app@postgres:5432/gmgn_twitter_intel",
        password_file,
    )

    assert dsn == "postgresql://gmgn_app:secret-pass@postgres:5432/gmgn_twitter_intel"


def test_local_docker_host_dsn_maps_compose_hostname_to_loopback(monkeypatch):
    monkeypatch.setenv("GMGN_POSTGRES_PORT", "56532")
    monkeypatch.setattr(postgres_client, "_running_in_container", lambda: False)

    dsn = local_docker_host_dsn("postgresql://gmgn_app:secret-pass@postgres:5432/gmgn_twitter_intel")

    assert dsn == "postgresql://gmgn_app:secret-pass@127.0.0.1:56532/gmgn_twitter_intel"


def test_local_docker_host_dsn_uses_uncontended_default_host_port(monkeypatch):
    monkeypatch.delenv("GMGN_POSTGRES_PORT", raising=False)
    monkeypatch.setattr(postgres_client, "_running_in_container", lambda: False)

    dsn = local_docker_host_dsn("postgresql://gmgn_app@postgres:5432/gmgn_twitter_intel")

    assert dsn == "postgresql://gmgn_app@127.0.0.1:56532/gmgn_twitter_intel"


def test_local_docker_host_dsn_keeps_container_service_hostname_in_container(monkeypatch):
    monkeypatch.setenv("GMGN_POSTGRES_PORT", "56532")
    monkeypatch.setattr(postgres_client, "_running_in_container", lambda: True)

    dsn = local_docker_host_dsn("postgresql://gmgn_app@postgres:5432/gmgn_twitter_intel")

    assert dsn == "postgresql://gmgn_app@postgres:5432/gmgn_twitter_intel"


def test_local_docker_host_dsn_maps_keyword_dsn_to_loopback(monkeypatch):
    monkeypatch.setenv("GMGN_POSTGRES_PORT", "56532")
    monkeypatch.setattr(postgres_client, "_running_in_container", lambda: False)

    dsn = local_docker_host_dsn("user=gmgn_app host=postgres port=5432 dbname=gmgn_twitter_intel")

    assert conninfo.conninfo_to_dict(dsn) == {
        "user": "gmgn_app",
        "dbname": "gmgn_twitter_intel",
        "host": "127.0.0.1",
        "port": "56532",
    }


def test_create_pool_uses_host_side_compose_dsn_mapping(monkeypatch):
    captured = {}

    class FakePool:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setenv("GMGN_POSTGRES_PORT", "56532")
    monkeypatch.setattr(postgres_client, "_running_in_container", lambda: False)
    monkeypatch.setattr(postgres_client, "ConnectionPool", FakePool)

    pool = create_pool(
        "postgresql://gmgn_app@postgres:5432/gmgn_twitter_intel",
        min_size=1,
        max_size=2,
        connect_timeout_seconds=5,
    )

    assert isinstance(pool, FakePool)
    assert captured["conninfo"] == "postgresql://gmgn_app@127.0.0.1:56532/gmgn_twitter_intel"


def test_postgres_health_check_reports_liveness_and_migration_version():
    payload = postgres_health_check(FakeConn())

    assert payload == {
        "ok": True,
        "probe": "postgres_liveness",
        "migration_version": "20260506_0003",
    }


def test_postgres_health_check_rejects_stale_migration_when_expected_version_is_set():
    payload = postgres_health_check(FakeConn(), expected_migration_version="20260508_0011")

    assert payload["ok"] is False
    assert payload["migration_version"] == "20260506_0003"
    assert payload["expected_migration_version"] == "20260508_0011"
    assert payload["migration_status"] == "stale"
