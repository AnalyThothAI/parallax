#!/usr/bin/env bash
set -euo pipefail

mkdir -p "${HOME}/.gmgn-twitter-intel/reports/pgbadger"
docker compose run --rm pgbadger
