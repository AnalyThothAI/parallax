#!/usr/bin/env bash
set -euo pipefail

mkdir -p "${HOME}/.parallax/reports/pgbadger"
docker compose run --rm pgbadger
