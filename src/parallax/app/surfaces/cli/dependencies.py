from __future__ import annotations

from contextlib import contextmanager

from parallax.app.runtime.repository_session import repositories_for_connection
from parallax.platform.db.postgres_client import connect_postgres, with_password_from_file


@contextmanager
def postgres_connection(settings):
    dsn = with_password_from_file(settings.postgres_dsn, settings.postgres_password_file)
    conn = connect_postgres(dsn, connect_timeout_seconds=settings.postgres_connect_timeout_seconds)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def repositories(settings):
    with postgres_connection(settings) as conn:
        yield repositories_for_connection(
            conn,
            notification_delivery_running_timeout_ms=int(settings.workers.notification_delivery.running_timeout_ms),
            notification_delivery_stale_running_terminalization_batch_size=int(
                settings.workers.notification_delivery.stale_running_terminalization_batch_size
            ),
        )
