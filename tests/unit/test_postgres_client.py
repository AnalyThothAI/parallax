from __future__ import annotations

import pytest
from psycopg import conninfo, pq

from parallax.platform.db import postgres_client
from parallax.platform.db.postgres_client import (
    create_pool,
    local_docker_host_dsn,
    postgres_health_check,
    postgres_liveness_check,
    require_transaction,
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
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    def execute(self, sql, params=None):
        return FakeCursor().execute(sql, params)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


class FakeConnWithoutCommit:
    def __init__(self) -> None:
        self.rollbacks = 0

    def execute(self, sql, params=None):
        return FakeCursor().execute(sql, params)

    def rollback(self) -> None:
        self.rollbacks += 1


class FakeFailingConnWithoutRollback:
    def execute(self, sql, params=None):
        raise RuntimeError("probe failed")


class FakeTransactionInfo:
    def __init__(self, status: pq.TransactionStatus) -> None:
        self.transaction_status = status


class FakeTransactionStatusConn:
    def __init__(self, status: pq.TransactionStatus) -> None:
        self.info = FakeTransactionInfo(status)


def test_with_password_from_file_replaces_password(tmp_path):
    password_file = tmp_path / "pg_password"
    password_file.write_text("secret-pass\n", encoding="utf-8")

    dsn = with_password_from_file(
        "postgresql://parallax_app:old-pass@postgres:5432/parallax",
        password_file,
    )

    assert dsn.startswith("postgresql://")
    assert "secret-pass" in dsn
    assert "old-pass" not in dsn


def test_with_password_from_file_injects_password_into_passwordless_dsn(tmp_path):
    password_file = tmp_path / "pg_password"
    password_file.write_text("secret-pass\n", encoding="utf-8")

    dsn = with_password_from_file(
        "postgresql://parallax_app@postgres:5432/parallax",
        password_file,
    )

    assert dsn == "postgresql://parallax_app:secret-pass@postgres:5432/parallax"


def test_local_docker_host_dsn_maps_compose_hostname_to_loopback(monkeypatch):
    monkeypatch.setenv("PARALLAX_POSTGRES_PORT", "56532")
    monkeypatch.setattr(postgres_client, "_running_in_container", lambda: False)

    dsn = local_docker_host_dsn("postgresql://parallax_app:secret-pass@postgres:5432/parallax")

    assert dsn == "postgresql://parallax_app:secret-pass@127.0.0.1:56532/parallax"


def test_local_docker_host_dsn_uses_uncontended_default_host_port(monkeypatch):
    monkeypatch.delenv("PARALLAX_POSTGRES_PORT", raising=False)
    monkeypatch.setattr(postgres_client, "_running_in_container", lambda: False)

    dsn = local_docker_host_dsn("postgresql://parallax_app@postgres:5432/parallax")

    assert dsn == "postgresql://parallax_app@127.0.0.1:56532/parallax"


def test_local_docker_host_dsn_keeps_container_service_hostname_in_container(monkeypatch):
    monkeypatch.setenv("PARALLAX_POSTGRES_PORT", "56532")
    monkeypatch.setattr(postgres_client, "_running_in_container", lambda: True)

    dsn = local_docker_host_dsn("postgresql://parallax_app@postgres:5432/parallax")

    assert dsn == "postgresql://parallax_app@postgres:5432/parallax"


def test_local_docker_host_dsn_maps_keyword_dsn_to_loopback(monkeypatch):
    monkeypatch.setenv("PARALLAX_POSTGRES_PORT", "56532")
    monkeypatch.setattr(postgres_client, "_running_in_container", lambda: False)

    dsn = local_docker_host_dsn("user=parallax_app host=postgres port=5432 dbname=parallax")

    assert conninfo.conninfo_to_dict(dsn) == {
        "user": "parallax_app",
        "dbname": "parallax",
        "host": "127.0.0.1",
        "port": "56532",
    }


def test_create_pool_uses_host_side_compose_dsn_mapping(monkeypatch):
    captured = {}

    class FakePool:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setenv("PARALLAX_POSTGRES_PORT", "56532")
    monkeypatch.setattr(postgres_client, "_running_in_container", lambda: False)
    monkeypatch.setattr(postgres_client, "ConnectionPool", FakePool)

    pool = create_pool(
        "postgresql://parallax_app@postgres:5432/parallax",
        min_size=1,
        max_size=2,
        connect_timeout_seconds=5,
    )

    assert isinstance(pool, FakePool)
    assert captured["conninfo"] == "postgresql://parallax_app@127.0.0.1:56532/parallax"


def test_create_pool_passes_application_timeouts_and_keepalives(monkeypatch):
    captured = {}

    class FakePool:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(postgres_client, "ConnectionPool", FakePool)

    create_pool(
        "postgresql://parallax_app@postgres:5432/parallax",
        min_size=1,
        max_size=2,
        connect_timeout_seconds=5,
        application_name="gmgn_worker",
        statement_timeout_seconds=30,
        idle_in_transaction_session_timeout_seconds=15,
        keepalives=True,
        keepalives_idle=20,
        keepalives_interval=5,
        keepalives_count=3,
    )

    kwargs = captured["kwargs"]
    assert kwargs["application_name"] == "gmgn_worker"
    assert kwargs["options"] == "-c statement_timeout=30000 -c idle_in_transaction_session_timeout=15000"
    assert kwargs["keepalives"] == 1
    assert kwargs["keepalives_idle"] == 20
    assert kwargs["keepalives_interval"] == 5
    assert kwargs["keepalives_count"] == 3


@pytest.mark.parametrize(
    ("timeout_field", "timeout_value"),
    [
        ("statement_timeout_seconds", -1),
        ("statement_timeout_seconds", True),
        ("statement_timeout_seconds", "30"),
        ("idle_in_transaction_session_timeout_seconds", -1),
        ("idle_in_transaction_session_timeout_seconds", True),
        ("idle_in_transaction_session_timeout_seconds", "15"),
    ],
)
def test_create_pool_rejects_malformed_runtime_timeouts_without_zero_ms_repair(
    timeout_field: str,
    timeout_value: object,
    monkeypatch,
) -> None:
    class FakePool:
        def __init__(self, **_kwargs):
            raise AssertionError("pool must not be created with malformed timeout")

    monkeypatch.setattr(postgres_client, "ConnectionPool", FakePool)

    with pytest.raises(ValueError, match="postgres_runtime_timeout_seconds_required"):
        create_pool(
            "postgresql://parallax_app@postgres:5432/parallax",
            min_size=1,
            max_size=2,
            connect_timeout_seconds=5,
            **{timeout_field: timeout_value},
        )


def test_postgres_health_check_reports_liveness_and_migration_version():
    conn = FakeConn()
    payload = postgres_health_check(conn)

    assert payload == {
        "ok": True,
        "probe": "postgres_liveness",
        "migration_version": "20260506_0003",
    }
    assert conn.commits == 1
    assert conn.rollbacks == 0


def test_postgres_liveness_check_does_not_requery_schema_version():
    class RecordingConn(FakeConn):
        def __init__(self) -> None:
            super().__init__()
            self.sql: list[str] = []

        def execute(self, sql, params=None):
            self.sql.append(str(sql))
            return super().execute(sql, params)

    conn = RecordingConn()

    payload = postgres_liveness_check(conn)

    assert payload == {"ok": True, "probe": "postgres_liveness"}
    assert conn.sql == ["SELECT 1 AS ok"]
    assert conn.commits == 1


def test_postgres_health_check_rejects_stale_migration_when_expected_version_is_set():
    payload = postgres_health_check(FakeConn(), expected_migration_version="20260508_0011")

    assert payload["ok"] is False
    assert payload["migration_version"] == "20260506_0003"
    assert payload["expected_migration_version"] == "20260508_0011"
    assert payload["migration_status"] == "stale"


def test_postgres_health_check_requires_commit_contract_without_optional_probe():
    conn = FakeConnWithoutCommit()

    payload = postgres_health_check(conn)

    assert payload["ok"] is False
    assert payload["probe"] == "postgres_liveness"
    assert payload["error"] == "AttributeError"
    assert "commit" in str(payload["detail"])
    assert conn.rollbacks == 1


def test_postgres_health_check_reports_missing_rollback_contract_without_optional_probe():
    payload = postgres_health_check(FakeFailingConnWithoutRollback())

    assert payload["ok"] is False
    assert payload["probe"] == "postgres_liveness"
    assert payload["error"] == "AttributeError"
    assert "rollback" in str(payload["detail"])
    assert payload["original_error"] == "RuntimeError"


def test_require_transaction_rejects_fake_connection_without_transaction_status_contract():
    with pytest.raises(RuntimeError, match="fake_write_requires_transaction_status_contract"):
        require_transaction(object(), operation="fake_write")


def test_require_transaction_rejects_idle_transaction_status():
    conn = FakeTransactionStatusConn(pq.TransactionStatus.IDLE)

    with pytest.raises(RuntimeError, match="projection_write_requires_explicit_transaction"):
        require_transaction(conn, operation="projection_write")


def test_require_transaction_accepts_active_transaction_status():
    conn = FakeTransactionStatusConn(pq.TransactionStatus.INTRANS)

    require_transaction(conn, operation="projection_write")
