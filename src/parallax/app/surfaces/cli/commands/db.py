from __future__ import annotations

from typing import Any

from parallax.app.runtime.repository_session import postgres_connection
from parallax.domains.token_intel.interfaces import TOKEN_RADAR_PROJECTION_VERSION
from parallax.platform.config.settings import load_settings
from parallax.platform.db.postgres_audit import PostgresOperationalAudit, PostgresQueryAudit
from parallax.platform.db.postgres_client import (
    local_docker_host_dsn,
    postgres_health_check,
    with_password_from_file,
)
from parallax.platform.db.postgres_migrations import latest_migration_version, upgrade_head


def handle_db(args: object) -> tuple[int, dict[str, Any]]:
    settings = load_settings(require_ws_token=False)
    if args.db_command == "migrate":
        dsn = local_docker_host_dsn(
            with_password_from_file(settings.storage.postgres.dsn, settings.postgres_password_file)
        )
        upgrade_head(dsn)
        return 0, {"ok": True, "data": {"migration": "head"}}

    if args.db_command == "health":
        with postgres_connection(settings) as conn:
            health = postgres_health_check(conn, expected_migration_version=latest_migration_version())
        return (0 if health.get("ok") else 1), {"ok": bool(health.get("ok")), "data": health}

    if args.db_command == "audit":
        with postgres_connection(settings) as conn:
            audit = PostgresOperationalAudit(conn).run()
        return (0 if audit.get("ok") else 1), {"ok": bool(audit.get("ok")), "data": audit}

    if args.db_command == "query-audit":
        with postgres_connection(settings) as conn:
            audit = PostgresQueryAudit(
                conn,
                token_radar_projection_version=TOKEN_RADAR_PROJECTION_VERSION,
            ).run(analyze=bool(args.analyze))
        return (0 if audit.get("ok") else 1), {"ok": bool(audit.get("ok")), "data": audit}

    return 2, {"ok": False, "error": f"unknown db command: {args.db_command}"}
