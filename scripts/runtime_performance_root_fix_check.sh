#!/usr/bin/env bash
set -euo pipefail

DB_SERVICE="${DB_SERVICE:-postgres}"
DB_USER="${DB_USER:-tracefold_app}"
DB_NAME="${DB_NAME:-tracefold}"
APP_URL="${APP_URL:-http://127.0.0.1:8765}"
TOKEN_RADAR_RANK_SOURCE_MAX_MS="${TOKEN_RADAR_RANK_SOURCE_MAX_MS:-100}"
TOKEN_RADAR_TEMP_BLOCKS_MAX="${TOKEN_RADAR_TEMP_BLOCKS_MAX:-0}"
TOKEN_RADAR_TOP_SQL_SHARE_MAX="${TOKEN_RADAR_TOP_SQL_SHARE_MAX:-10}"
TOKEN_RADAR_EVENT_ID_POPULATE_MIN_CALLS="${TOKEN_RADAR_EVENT_ID_POPULATE_MIN_CALLS:-1}"

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

assert_int_ge() {
  local label="$1"
  local value="$2"
  local min="$3"
  if ! awk -v value="${value}" -v min="${min}" 'BEGIN { exit !(value >= min) }'; then
    record_failure "${label} ${value} is below ${min}"
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

assert_zero_new_or_cumulative_calls() {
  local label="$1"
  local current_calls="$2"
  local before_calls="${3:-}"
  if [[ -n "${before_calls}" ]]; then
    local delta=$((current_calls - before_calls))
    echo "${label} call delta=${delta}"
    assert_int_le "${label} call delta" "${delta}" 0
  else
    echo "${label} before snapshot unset; requiring cumulative calls to be zero."
    assert_int_le "${label} cumulative calls" "${current_calls}" 0
  fi
}

echo "== readyz =="
curl -fsS "${APP_URL}/readyz"
echo

echo "== migration =="
psql_cmd -Atc "SELECT version_num FROM alembic_version ORDER BY version_num DESC LIMIT 1;"

echo "== postgres observability extensions =="
observability_extensions="$(
  psql_cmd -Atc "
SELECT extname
FROM pg_extension
WHERE extname = ANY(
  ARRAY[
    'pg_stat_statements',
    'pg_stat_kcache',
    'pg_qualstats',
    'pg_wait_sampling'
  ]::name[]
)
ORDER BY extname;"
)"
printf '%s\n' "${observability_extensions}"
for extension_name in pg_stat_statements pg_stat_kcache pg_qualstats pg_wait_sampling; do
  if ! printf '%s\n' "${observability_extensions}" | grep -qx "${extension_name}"; then
    record_failure "PostgreSQL extension ${extension_name} is not installed in ${DB_NAME}"
  fi
done

if [[ "${failures}" -gt 0 ]]; then
  echo "runtime performance root fix check failed: ${failures} hard gate(s) failed" >&2
  exit 1
fi

echo "== token radar event-id bounded population calls =="
token_radar_event_id_populate_calls="$(
  psql_cmd -Atc "
SELECT COALESCE(sum(calls), 0)
FROM pg_stat_statements
WHERE query ILIKE '%INSERT INTO token_radar_rank_source_events%'
  AND query ILIKE '%source_event_ids_json%'
  AND query ILIKE '%requested_event_ids%'
  AND query ILIKE '%jsonb_array_elements_text%'
  AND query ILIKE '%token_intents.event_id = requested_event_ids.source_event_id%';"
)"
echo "${token_radar_event_id_populate_calls}"
if [[ "${TOKEN_RADAR_EVENT_ID_POPULATE_MIN_CALLS}" -gt 0 ]]; then
  assert_int_ge "token radar event-id bounded population calls" \
    "${token_radar_event_id_populate_calls}" "${TOKEN_RADAR_EVENT_ID_POPULATE_MIN_CALLS}"
else
  echo "TOKEN_RADAR_EVENT_ID_POPULATE_MIN_CALLS=0; existence gate disabled for dry checks."
fi

echo "== old token radar target-wide source population calls =="
old_token_radar_source_populate_calls="$(
  psql_cmd -Atc "
SELECT COALESCE(sum(calls), 0)
FROM pg_stat_statements
WHERE query ILIKE '%INSERT INTO token_radar_rank_source_events%'
  AND query ILIKE '%source_intents%'
  AND query NOT ILIKE '%source_event_ids_json%'
  AND query NOT ILIKE '%requested_event_ids%';"
)"
echo "${old_token_radar_source_populate_calls}"
assert_zero_new_or_cumulative_calls "old token radar target-wide source population" \
  "${old_token_radar_source_populate_calls}" "${OLD_TOKEN_RADAR_SOURCE_POPULATE_CALLS_BEFORE:-}"

echo "== token radar rank source mean proxy =="
rank_source_mean_proxy="$(
  psql_cmd -Atc "
WITH ranked AS (
  SELECT mean_exec_time, calls
  FROM pg_stat_statements
  WHERE query ILIKE '%INSERT INTO token_radar_rank_source_events%'
    AND query ILIKE '%source_event_ids_json%'
    AND query ILIKE '%requested_event_ids%'
    AND query ILIKE '%jsonb_array_elements_text%'
    AND NOT (
      query ILIKE '%count(*)%'
      AND query ILIKE '%source_payload_hash IS NULL%'
    )
  ORDER BY total_exec_time DESC
  LIMIT 20
)
SELECT COALESCE(round(max(mean_exec_time)::numeric, 2), 0)
FROM ranked;"
)"
echo "${rank_source_mean_proxy}"
assert_decimal_le "token radar rank source mean proxy ms" \
  "${rank_source_mean_proxy}" "${TOKEN_RADAR_RANK_SOURCE_MAX_MS}"

echo "== token radar temp blocks =="
token_radar_temp_blocks="$(
  psql_cmd -Atc "
SELECT COALESCE(sum(temp_blks_written), 0)
FROM pg_stat_statements
WHERE query ILIKE '%INSERT INTO token_radar_rank_source_events%'
  AND query ILIKE '%source_event_ids_json%'
  AND query ILIKE '%requested_event_ids%'
  AND query ILIKE '%jsonb_array_elements_text%'
  AND NOT (
    query ILIKE '%count(*)%'
    AND query ILIKE '%source_payload_hash IS NULL%'
  );"
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
echo "TOKEN_RADAR_TOP_SQL_SHARE_MAX=${TOKEN_RADAR_TOP_SQL_SHARE_MAX}; broad SQL share is report-only."

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
      WHEN stat.relname IN ('events', 'enriched_events')
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
