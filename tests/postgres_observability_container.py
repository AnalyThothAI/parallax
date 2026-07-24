from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEST_POSTGRES_IMAGE = "tracefold-postgres-observability:18"
TEST_POSTGRES_IMAGE = os.environ.get("TRACEFOLD_TEST_POSTGRES_IMAGE", DEFAULT_TEST_POSTGRES_IMAGE)
OBSERVABILITY_POSTGRES_COMMAND = [
    "postgres",
    "-c",
    "shared_preload_libraries=pg_stat_statements,pg_stat_kcache,pg_qualstats,pg_wait_sampling",
    "-c",
    "pg_stat_statements.track=all",
]


def observability_postgres_container(postgres_container_cls: type[Any]) -> Any:
    _ensure_observability_image()
    return postgres_container_cls(TEST_POSTGRES_IMAGE).with_command(OBSERVABILITY_POSTGRES_COMMAND)


def _ensure_observability_image() -> None:
    if TEST_POSTGRES_IMAGE != DEFAULT_TEST_POSTGRES_IMAGE:
        return
    inspect_result = subprocess.run(
        ["docker", "image", "inspect", TEST_POSTGRES_IMAGE],
        capture_output=True,
        check=False,
        text=True,
    )
    if inspect_result.returncode == 0:
        return
    subprocess.run(
        [
            "docker",
            "build",
            "-t",
            TEST_POSTGRES_IMAGE,
            "-f",
            str(ROOT / "ops" / "postgres" / "Dockerfile"),
            str(ROOT),
        ],
        check=True,
    )
