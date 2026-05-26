#!/usr/bin/env bash
set -euo pipefail

SNAPSHOT_COUNT="${POWA_SNAPSHOT_COUNT:-6}"

if ! [[ "${SNAPSHOT_COUNT}" =~ ^[0-9]+$ ]] || [ "${SNAPSHOT_COUNT}" -lt 1 ]; then
  echo "POWA_SNAPSHOT_COUNT must be a positive integer" >&2
  exit 2
fi

docker compose exec -T postgres psql -U gmgn_app -d powa -v ON_ERROR_STOP=1 \
  -v snapshot_count="${SNAPSHOT_COUNT}" <<'SQL'
ALTER SYSTEM SET powa.coalesce = '5';
ALTER SYSTEM SET powa.frequency = '5min';
SELECT pg_reload_conf() AS config_reloaded;

UPDATE powa_servers
SET frequency = 300,
    powa_coalesce = 5,
    retention = interval '7 days'
WHERE id = 0;

SELECT
  id,
  hostname,
  port,
  username,
  dbname,
  frequency,
  powa_coalesce,
  retention
FROM powa_servers
WHERE id = 0;

WITH snapshots AS (
  SELECT powa_take_snapshot(0)
  FROM generate_series(1, :snapshot_count)
)
SELECT count(*) AS snapshots_taken
FROM snapshots;

SELECT count(*) AS current_rows
FROM powa_statements_history_current;

SELECT count(*) AS history_rows
FROM powa_statements_history;

DO $$
DECLARE
  current_rows bigint;
  history_rows bigint;
BEGIN
  SELECT count(*) INTO current_rows
  FROM powa_statements_history_current;

  SELECT count(*) INTO history_rows
  FROM powa_statements_history;

  IF history_rows <= 0 THEN
    RAISE EXCEPTION 'powa_statements_history has no coalesced local-server statement data';
  END IF;

  IF current_rows + history_rows <= 0 THEN
    RAISE EXCEPTION 'PoWA has no local-server statement data';
  END IF;
END $$;
SQL
