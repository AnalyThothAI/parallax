#!/usr/bin/env bash
set -euo pipefail

DB_SERVICE="${DB_SERVICE:-postgres}"
DB_USER="${DB_USER:-gmgn_app}"
DB_NAME="${DB_NAME:-gmgn_twitter_intel}"
APP_URL="${APP_URL:-http://127.0.0.1:8765}"
TOKEN_RADAR_RANK_SOURCE_MAX_MS="${TOKEN_RADAR_RANK_SOURCE_MAX_MS:-100}"
TOKEN_RADAR_TEMP_BLOCKS_MAX="${TOKEN_RADAR_TEMP_BLOCKS_MAX:-0}"
STALE_EQUITY_FETCH_RUNS_MAX="${STALE_EQUITY_FETCH_RUNS_MAX:-0}"
TOKEN_RADAR_TOP_SQL_SHARE_MAX="${TOKEN_RADAR_TOP_SQL_SHARE_MAX:-10}"

psql_cmd() {
  docker compose exec -T "${DB_SERVICE}" psql -U "${DB_USER}" -d "${DB_NAME}" "$@"
}

failures=0

record_failure() {
  echo "FAIL: $*" >&2
  failures=$((failures + 1))
}

assert_int_le() {
  local label="$1"
  local value="$2"
  local max="$3"
  if ! awk -v value="${value}" -v max="${max}" 'BEGIN { exit !(value <= max) }'; then
    record_failure "${label} ${value} exceeds ${max}"
  fi
}

assert_decimal_le() {
  local label="$1"
  local value="$2"
  local max="$3"
  if ! awk -v value="${value}" -v max="${max}" 'BEGIN { exit !(value <= max) }'; then
    record_failure "${label} ${value} exceeds ${max}"
  fi
}

echo "== readyz =="
curl -fsS "${APP_URL}/readyz"
echo

echo "== migration =="
psql_cmd -Atc "SELECT version_num FROM alembic_version ORDER BY version_num DESC LIMIT 1;"

echo "== old token radar query calls =="
old_token_radar_calls="$(
  psql_cmd -Atc "
SELECT COALESCE(sum(calls), 0)
FROM pg_stat_statements
WHERE query ILIKE 'WITH request_targets AS (%';"
)"
echo "${old_token_radar_calls}"
if [[ -n "${OLD_TOKEN_RADAR_CALLS_BEFORE:-}" ]]; then
  old_token_radar_delta=$((old_token_radar_calls - OLD_TOKEN_RADAR_CALLS_BEFORE))
  echo "old token radar query call delta=${old_token_radar_delta}"
  assert_int_le "old token radar query call delta" "${old_token_radar_delta}" 0
else
  echo "OLD_TOKEN_RADAR_CALLS_BEFORE unset; printed cumulative calls only."
fi

echo "== token radar rank source mean proxy =="
rank_source_mean_proxy="$(
  psql_cmd -Atc "
WITH ranked AS (
  SELECT mean_exec_time, calls
  FROM pg_stat_statements
  WHERE query ILIKE '%token_radar_rank_source_events%'
  ORDER BY total_exec_time DESC
  LIMIT 20
)
SELECT COALESCE(round(max(mean_exec_time)::numeric, 2), 0)
FROM ranked;"
)"
echo "${rank_source_mean_proxy}"
assert_decimal_le "token radar rank source mean proxy ms" \
  "${rank_source_mean_proxy}" "${TOKEN_RADAR_RANK_SOURCE_MAX_MS}"

echo "== stale equity fetch runs =="
stale_equity_fetch_runs="$(
  psql_cmd -Atc "
SELECT count(*)
FROM equity_event_fetch_runs
WHERE status = 'running'
  AND started_at_ms < ((extract(epoch FROM clock_timestamp()) * 1000)::bigint - 900000);"
)"
echo "${stale_equity_fetch_runs}"
assert_int_le "stale equity fetch runs" "${stale_equity_fetch_runs}" "${STALE_EQUITY_FETCH_RUNS_MAX}"

echo "== token radar temp blocks =="
token_radar_temp_blocks="$(
  psql_cmd -Atc "
SELECT COALESCE(sum(temp_blks_written), 0)
FROM pg_stat_statements
WHERE query ILIKE '%token_radar_rank_source_events%';"
)"
echo "${token_radar_temp_blocks}"
assert_int_le "token radar temp blocks" "${token_radar_temp_blocks}" "${TOKEN_RADAR_TEMP_BLOCKS_MAX}"

echo "== top sql token radar share =="
token_radar_top_sql_share="$(
  psql_cmd -Atc "
WITH totals AS (
  SELECT sum(total_exec_time) AS all_ms
  FROM pg_stat_statements
),
token AS (
  SELECT COALESCE(max(total_exec_time), 0) AS token_ms
  FROM pg_stat_statements
  WHERE query ILIKE '%token_radar%'
)
SELECT CASE
  WHEN totals.all_ms IS NULL OR totals.all_ms = 0 THEN 0
  ELSE round((token.token_ms / totals.all_ms * 100)::numeric, 2)
END
FROM totals, token;"
)"
echo "${token_radar_top_sql_share}"
assert_decimal_le "top sql token radar share percent" \
  "${token_radar_top_sql_share}" "${TOKEN_RADAR_TOP_SQL_SHARE_MAX}"

echo "== postgres lifecycle report =="
psql_cmd --csv -c "
WITH lifecycle_targets AS (
  SELECT
    stat.relid,
    stat.relname AS table_name,
    stat.n_live_tup AS live_rows,
    stat.n_dead_tup AS dead_rows,
    GREATEST(stat.last_analyze, stat.last_autoanalyze) AS last_analyze,
    CASE
      WHEN stat.relname IN (
        'token_radar_rank_source_events',
        'token_radar_target_features',
        'token_radar_current_rows',
        'token_radar_publication_state'
      )
        THEN 'hot compact rank/read path'
      WHEN stat.relname IN ('events', 'enriched_events', 'equity_event_evidence_artifacts')
        THEN 'selected-row hydrate'
      WHEN stat.relname = 'raw_frames'
        THEN 'cold audit/history'
      ELSE 'unknown'
    END AS retention_class
  FROM pg_stat_user_tables stat
  WHERE stat.relname IN (
      'raw_frames',
      'events',
      'enriched_events',
      'equity_event_evidence_artifacts',
      'token_radar_rank_source_events',
      'token_radar_target_features',
      'token_radar_current_rows',
      'token_radar_publication_state'
    )
)
SELECT
  table_name,
  pg_total_relation_size(relid) AS total_bytes,
  live_rows,
  dead_rows,
  last_analyze,
  retention_class,
  CASE retention_class
    WHEN 'hot compact rank/read path'
      THEN 'verify compact indexed claim/read path and analyze after owner-path rebuild'
    WHEN 'selected-row hydrate'
      THEN 'verify access follows ranking or document selection by stable key'
    WHEN 'cold audit/history'
      THEN 'review retention window and partition lifecycle plan before operator maintenance'
    ELSE 'classify lifecycle owner before changing maintenance policy'
  END AS recommended_action
FROM lifecycle_targets
ORDER BY
  CASE retention_class
    WHEN 'hot compact rank/read path' THEN 1
    WHEN 'selected-row hydrate' THEN 2
    WHEN 'cold audit/history' THEN 3
    ELSE 4
  END,
  table_name;"

if [[ "${failures}" -gt 0 ]]; then
  echo "runtime performance root fix check failed: ${failures} hard gate(s) failed" >&2
  exit 1
fi

echo "runtime performance root fix check passed"
