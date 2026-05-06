from __future__ import annotations

from gmgn_twitter_intel.storage.postgres_client import postgres_health_check, with_password_from_file


class FakeCursor:
    def __init__(self) -> None:
        self.last_sql = ""

    def execute(self, sql, params=None):
        self.last_sql = str(sql)
        return self

    def fetchone(self):
        if "alembic_version" in self.last_sql:
            return {"version_num": "20260506_0001"}
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


def test_postgres_health_check_reports_liveness_and_migration_version():
    payload = postgres_health_check(FakeConn())

    assert payload == {
        "ok": True,
        "probe": "postgres_liveness",
        "migration_version": "20260506_0001",
    }
