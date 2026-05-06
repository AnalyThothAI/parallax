from __future__ import annotations

from pathlib import Path

import yaml


def test_compose_runs_postgres_and_migration_before_app() -> None:
    compose = yaml.safe_load(Path("compose.yaml").read_text())
    services = compose["services"]

    assert "postgres" in services
    assert "migrate" in services
    assert services["postgres"]["image"].startswith("postgres:")
    assert services["postgres"]["healthcheck"]["test"][0] == "CMD-SHELL"
    assert "pg_isready" in services["postgres"]["healthcheck"]["test"][1]

    app_depends = services["app"]["depends_on"]
    assert app_depends["postgres"]["condition"] == "service_healthy"
    assert app_depends["migrate"]["condition"] == "service_completed_successfully"
    assert services["app"]["healthcheck"]["test"][2] == "-c"
    assert "/healthz" in services["app"]["healthcheck"]["test"][3]


def test_compose_no_longer_mounts_sqlite_data_volume_into_app() -> None:
    compose = yaml.safe_load(Path("compose.yaml").read_text())
    app_volumes = compose["services"]["app"].get("volumes", [])

    assert all("/root/.gmgn-twitter-intel/data" not in volume for volume in app_volumes)
    assert "gmgn-twitter-intel-postgres" in compose["volumes"]
