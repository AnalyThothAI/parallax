#!/usr/bin/env bash
set -euo pipefail

mkdir -p "${HOME}/.tracefold/reports/pgbadger"
docker compose run --rm pgbadger
