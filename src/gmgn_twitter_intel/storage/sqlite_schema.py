from __future__ import annotations

import sqlite3
import time

SCHEMA_VERSION = 12

APP_TABLES = (
    "schema_migrations",
    "raw_frames",
    "events",
    "event_fts",
    "event_entities",
    "tokens",
    "token_aliases",
    "token_market_snapshots",
    "account_token_alerts",
    "event_token_mentions",
    "event_token_attributions",
    "token_market_observations",
    "enrichment_jobs",
    "model_runs",
    "social_event_extractions",
    "attention_seeds",
    "event_clusters",
    "harness_snapshots",
    "harness_decisions",
    "harness_outcomes",
    "harness_credits",
    "harness_weights",
    "notifications",
    "notification_reads",
    "notification_deliveries",
    "account_profiles",
    "account_token_call_stats",
    "account_quality_snapshots",
)

LEGACY_TABLES = (
    "event_enrichments",
    "event_token_candidates",
    "event_narratives",
    "account_narrative_alerts",
    "narrative_windows",
    "narrative_seeds",
    "narrative_token_links",
)

REQUIRED_COLUMNS: dict[str, set[str]] = {}

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
  version INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  applied_at_ms INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS raw_frames (
  frame_id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  channel TEXT NOT NULL,
  received_at_ms INTEGER NOT NULL,
  payload_hash TEXT NOT NULL UNIQUE,
  raw_payload_json TEXT NOT NULL,
  created_at_ms INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_raw_frames_received ON raw_frames(received_at_ms);
CREATE INDEX IF NOT EXISTS idx_raw_frames_channel_received ON raw_frames(channel, received_at_ms);

CREATE TABLE IF NOT EXISTS events (
  event_id TEXT PRIMARY KEY,
  logical_dedup_key TEXT NOT NULL UNIQUE,
  canonical_url TEXT,
  source_provider TEXT NOT NULL,
  source_transport TEXT NOT NULL,
  coverage TEXT NOT NULL,
  channel TEXT NOT NULL,
  action TEXT NOT NULL,
  original_action TEXT,
  tweet_id TEXT,
  internal_id TEXT,
  timestamp_ms INTEGER NOT NULL,
  received_at_ms INTEGER NOT NULL,
  author_handle TEXT,
  author_name TEXT,
  author_avatar TEXT,
  author_followers INTEGER,
  author_tags_json TEXT NOT NULL DEFAULT '[]',
  text TEXT,
  text_raw TEXT,
  text_clean TEXT,
  search_text TEXT,
  urls_json TEXT NOT NULL DEFAULT '[]',
  cashtags_json TEXT NOT NULL DEFAULT '[]',
  hashtags_json TEXT NOT NULL DEFAULT '[]',
  mentions_json TEXT NOT NULL DEFAULT '[]',
  media_json TEXT NOT NULL DEFAULT '[]',
  reference_json TEXT,
  matched_handles_json TEXT NOT NULL DEFAULT '[]',
  is_watched INTEGER NOT NULL DEFAULT 0,
  matched_at_ms INTEGER NOT NULL DEFAULT 0,
  raw_json TEXT NOT NULL,
  event_json TEXT NOT NULL,
  created_at_ms INTEGER NOT NULL,
  updated_at_ms INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_received ON events(received_at_ms);
CREATE INDEX IF NOT EXISTS idx_events_author_received ON events(author_handle, received_at_ms);
CREATE INDEX IF NOT EXISTS idx_events_watched_received ON events(is_watched, received_at_ms);
CREATE INDEX IF NOT EXISTS idx_events_tweet_id ON events(tweet_id);

CREATE VIRTUAL TABLE IF NOT EXISTS event_fts USING fts5(
  event_id UNINDEXED,
  author_handle,
  text_clean,
  search_text,
  cashtags,
  hashtags,
  mentions,
  tokenize = 'unicode61 remove_diacritics 2'
);

CREATE TABLE IF NOT EXISTS event_entities (
  entity_id TEXT PRIMARY KEY,
  event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
  entity_type TEXT NOT NULL,
  raw_value TEXT NOT NULL,
  normalized_value TEXT NOT NULL,
  chain TEXT,
  token_resolution_status TEXT NOT NULL,
  confidence REAL NOT NULL,
  source TEXT NOT NULL,
  received_at_ms INTEGER NOT NULL,
  author_handle TEXT,
  is_watched INTEGER NOT NULL DEFAULT 0,
  created_at_ms INTEGER NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_event_entities_event_type_value_chain
  ON event_entities(event_id, entity_type, normalized_value, COALESCE(chain, ''));
CREATE INDEX IF NOT EXISTS idx_event_entities_type_value ON event_entities(entity_type, normalized_value);
CREATE INDEX IF NOT EXISTS idx_event_entities_token_window
  ON event_entities(entity_type, token_resolution_status, received_at_ms);
CREATE INDEX IF NOT EXISTS idx_event_entities_watched_window ON event_entities(is_watched, received_at_ms);

CREATE TABLE IF NOT EXISTS tokens (
  token_id TEXT PRIMARY KEY,
  chain TEXT NOT NULL,
  address TEXT NOT NULL,
  symbol TEXT NOT NULL,
  name TEXT,
  icon_url TEXT,
  identity_status TEXT NOT NULL,
  first_seen_event_id TEXT,
  first_seen_ms INTEGER NOT NULL,
  created_at_ms INTEGER NOT NULL,
  updated_at_ms INTEGER NOT NULL,
  UNIQUE(chain, address)
);

CREATE INDEX IF NOT EXISTS idx_tokens_symbol ON tokens(symbol);
CREATE INDEX IF NOT EXISTS idx_tokens_lower_address ON tokens(lower(address));

CREATE TABLE IF NOT EXISTS token_aliases (
  alias_id TEXT PRIMARY KEY,
  symbol TEXT NOT NULL,
  token_id TEXT NOT NULL REFERENCES tokens(token_id) ON DELETE CASCADE,
  chain TEXT NOT NULL,
  address TEXT NOT NULL,
  source TEXT NOT NULL,
  confidence REAL NOT NULL,
  created_at_ms INTEGER NOT NULL,
  updated_at_ms INTEGER NOT NULL,
  UNIQUE(symbol, token_id)
);

CREATE INDEX IF NOT EXISTS idx_token_aliases_symbol ON token_aliases(symbol);
CREATE INDEX IF NOT EXISTS idx_token_aliases_token_id ON token_aliases(token_id);

CREATE TABLE IF NOT EXISTS token_market_snapshots (
  snapshot_id TEXT PRIMARY KEY,
  token_id TEXT NOT NULL REFERENCES tokens(token_id) ON DELETE CASCADE,
  event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
  price REAL,
  previous_price REAL,
  market_cap REAL,
  source_channel TEXT NOT NULL,
  received_at_ms INTEGER NOT NULL,
  raw_json TEXT NOT NULL,
  created_at_ms INTEGER NOT NULL,
  UNIQUE(token_id, event_id)
);

CREATE INDEX IF NOT EXISTS idx_token_market_snapshots_token_received
  ON token_market_snapshots(token_id, received_at_ms);

CREATE TABLE IF NOT EXISTS account_token_alerts (
  alert_id TEXT PRIMARY KEY,
  event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
  author_handle TEXT NOT NULL,
  entity_key TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  normalized_value TEXT NOT NULL,
  chain TEXT,
  token_resolution_status TEXT NOT NULL,
  is_first_seen_global INTEGER NOT NULL,
  is_first_seen_by_author INTEGER NOT NULL,
  received_at_ms INTEGER NOT NULL,
  created_at_ms INTEGER NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_account_token_alert_event_entity
  ON account_token_alerts(event_id, entity_key);
CREATE INDEX IF NOT EXISTS idx_account_token_alerts_received ON account_token_alerts(received_at_ms);
CREATE INDEX IF NOT EXISTS idx_account_token_alerts_author_received
  ON account_token_alerts(author_handle, received_at_ms);

CREATE TABLE IF NOT EXISTS event_token_mentions (
  mention_id TEXT PRIMARY KEY,
  event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
  identity_key TEXT NOT NULL,
  token_id TEXT,
  identity_status TEXT NOT NULL,
  chain TEXT,
  address TEXT,
  symbol TEXT NOT NULL,
  source TEXT NOT NULL,
  received_at_ms INTEGER NOT NULL,
  author_handle TEXT,
  author_followers INTEGER,
  is_watched INTEGER NOT NULL DEFAULT 0,
  created_at_ms INTEGER NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_event_token_mentions_event_identity
  ON event_token_mentions(event_id, identity_key);
CREATE INDEX IF NOT EXISTS idx_event_token_mentions_received
  ON event_token_mentions(received_at_ms);
CREATE INDEX IF NOT EXISTS idx_event_token_mentions_identity_received
  ON event_token_mentions(identity_key, received_at_ms);
CREATE INDEX IF NOT EXISTS idx_event_token_mentions_token_received
  ON event_token_mentions(token_id, received_at_ms);
CREATE INDEX IF NOT EXISTS idx_event_token_mentions_symbol_received
  ON event_token_mentions(symbol, received_at_ms);
CREATE INDEX IF NOT EXISTS idx_event_token_mentions_address_received
  ON event_token_mentions(lower(address), received_at_ms);
CREATE INDEX IF NOT EXISTS idx_event_token_mentions_identity_author_received
  ON event_token_mentions(identity_key, author_handle, received_at_ms);

CREATE TABLE IF NOT EXISTS event_token_attributions (
  attribution_id TEXT PRIMARY KEY,
  mention_id TEXT NOT NULL REFERENCES event_token_mentions(mention_id) ON DELETE CASCADE,
  event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
  mention_identity_key TEXT NOT NULL,
  identity_key TEXT NOT NULL,
  token_id TEXT,
  identity_status TEXT NOT NULL,
  chain TEXT,
  address TEXT,
  symbol TEXT NOT NULL,
  source TEXT NOT NULL,
  attribution_status TEXT NOT NULL,
  attribution_confidence REAL NOT NULL,
  attribution_weight REAL NOT NULL,
  attribution_rank INTEGER NOT NULL,
  candidate_count INTEGER NOT NULL,
  score_features_json TEXT NOT NULL DEFAULT '{}',
  reasons_json TEXT NOT NULL DEFAULT '[]',
  risks_json TEXT NOT NULL DEFAULT '[]',
  received_at_ms INTEGER NOT NULL,
  author_handle TEXT,
  author_followers INTEGER,
  is_watched INTEGER NOT NULL DEFAULT 0,
  created_at_ms INTEGER NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_event_token_attributions_mention_rank
  ON event_token_attributions(mention_id, attribution_rank);
CREATE INDEX IF NOT EXISTS idx_event_token_attributions_token_received
  ON event_token_attributions(token_id, received_at_ms);
CREATE INDEX IF NOT EXISTS idx_event_token_attributions_symbol_received
  ON event_token_attributions(symbol, received_at_ms);
CREATE INDEX IF NOT EXISTS idx_event_token_attributions_status_received
  ON event_token_attributions(attribution_status, received_at_ms);
CREATE INDEX IF NOT EXISTS idx_event_token_attributions_identity_author_received
  ON event_token_attributions(identity_key, author_handle, received_at_ms);
CREATE INDEX IF NOT EXISTS idx_event_token_attributions_posts_recent
  ON event_token_attributions(token_id, received_at_ms DESC, event_id DESC)
  WHERE token_id IS NOT NULL
    AND attribution_status IN ('direct', 'selected')
    AND attribution_weight > 0
    AND chain IS NOT NULL
    AND address IS NOT NULL
    AND chain NOT IN ('unknown', 'evm', 'evm_unknown');
CREATE INDEX IF NOT EXISTS idx_event_token_attributions_posts_ca_recent
  ON event_token_attributions(chain, address, received_at_ms DESC, event_id DESC)
  WHERE token_id IS NOT NULL
    AND attribution_status IN ('direct', 'selected')
    AND attribution_weight > 0
    AND chain IS NOT NULL
    AND address IS NOT NULL
    AND chain NOT IN ('unknown', 'evm', 'evm_unknown');

CREATE TABLE IF NOT EXISTS token_market_observations (
  observation_id TEXT PRIMARY KEY,
  attribution_id TEXT NOT NULL REFERENCES event_token_attributions(attribution_id) ON DELETE CASCADE,
  event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
  token_id TEXT NOT NULL REFERENCES tokens(token_id) ON DELETE CASCADE,
  chain TEXT NOT NULL,
  address TEXT NOT NULL,
  symbol TEXT NOT NULL,
  target_received_at_ms INTEGER NOT NULL,
  status TEXT NOT NULL,
  priority INTEGER NOT NULL DEFAULT 100,
  provider TEXT,
  source_channel TEXT NOT NULL DEFAULT 'gmgn_openapi_token_info',
  snapshot_id TEXT,
  attempt_count INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 5,
  next_run_at_ms INTEGER NOT NULL,
  last_error TEXT,
  created_at_ms INTEGER NOT NULL,
  updated_at_ms INTEGER NOT NULL,
  UNIQUE(attribution_id)
);

CREATE INDEX IF NOT EXISTS idx_token_market_observations_status_next
  ON token_market_observations(status, next_run_at_ms, priority);
CREATE INDEX IF NOT EXISTS idx_token_market_observations_token_target
  ON token_market_observations(token_id, target_received_at_ms);
CREATE INDEX IF NOT EXISTS idx_token_market_observations_event
  ON token_market_observations(event_id);

CREATE TABLE IF NOT EXISTS enrichment_jobs (
  job_id TEXT PRIMARY KEY,
  event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
  job_type TEXT NOT NULL,
  priority INTEGER NOT NULL,
  status TEXT NOT NULL,
  attempt_count INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 3,
  next_run_at_ms INTEGER NOT NULL,
  last_error TEXT,
  created_at_ms INTEGER NOT NULL,
  updated_at_ms INTEGER NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_enrichment_jobs_event_type
  ON enrichment_jobs(event_id, job_type);
CREATE INDEX IF NOT EXISTS idx_enrichment_jobs_status_next
  ON enrichment_jobs(status, next_run_at_ms, priority);

CREATE TABLE IF NOT EXISTS model_runs (
  run_id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL REFERENCES enrichment_jobs(job_id) ON DELETE CASCADE,
  event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  status TEXT NOT NULL,
  request_json TEXT NOT NULL,
  response_json TEXT,
  error TEXT,
  started_at_ms INTEGER NOT NULL,
  finished_at_ms INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_model_runs_event ON model_runs(event_id, finished_at_ms);

CREATE TABLE IF NOT EXISTS social_event_extractions (
  extraction_id TEXT PRIMARY KEY,
  event_id TEXT NOT NULL UNIQUE,
  run_id TEXT,
  author_handle TEXT,
  received_at_ms INTEGER NOT NULL,
  schema_version TEXT NOT NULL,
  model_version TEXT NOT NULL,
  event_type TEXT NOT NULL,
  source_action TEXT NOT NULL,
  subject TEXT NOT NULL,
  direction_hint TEXT NOT NULL,
  attention_mechanism TEXT NOT NULL,
  impact_hint REAL NOT NULL,
  semantic_novelty_hint REAL NOT NULL,
  confidence REAL NOT NULL,
  is_signal_event INTEGER NOT NULL,
  anchor_terms_json TEXT NOT NULL,
  token_candidates_json TEXT NOT NULL,
  semantic_risks_json TEXT NOT NULL,
  summary_zh TEXT NOT NULL,
  raw_response_json TEXT NOT NULL,
  created_at_ms INTEGER NOT NULL,
  updated_at_ms INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_social_event_extractions_received
  ON social_event_extractions(received_at_ms);
CREATE INDEX IF NOT EXISTS idx_social_event_extractions_author_received
  ON social_event_extractions(author_handle, received_at_ms);
CREATE INDEX IF NOT EXISTS idx_social_event_extractions_type_received
  ON social_event_extractions(event_type, received_at_ms);

CREATE TABLE IF NOT EXISTS attention_seeds (
  seed_id TEXT PRIMARY KEY,
  extraction_id TEXT NOT NULL REFERENCES social_event_extractions(extraction_id) ON DELETE CASCADE,
  event_id TEXT NOT NULL,
  author_handle TEXT,
  received_at_ms INTEGER NOT NULL,
  event_type TEXT NOT NULL,
  subject TEXT NOT NULL,
  anchor_terms_json TEXT NOT NULL,
  token_uptake_count INTEGER NOT NULL DEFAULT 0,
  top_linked_symbols_json TEXT NOT NULL DEFAULT '[]',
  seed_status TEXT NOT NULL,
  risks_json TEXT NOT NULL DEFAULT '[]',
  created_at_ms INTEGER NOT NULL,
  updated_at_ms INTEGER NOT NULL,
  UNIQUE(extraction_id)
);

CREATE INDEX IF NOT EXISTS idx_attention_seeds_received ON attention_seeds(received_at_ms);
CREATE INDEX IF NOT EXISTS idx_attention_seeds_author_received ON attention_seeds(author_handle, received_at_ms);

CREATE TABLE IF NOT EXISTS event_clusters (
  cluster_id TEXT PRIMARY KEY,
  seed_id TEXT REFERENCES attention_seeds(seed_id) ON DELETE SET NULL,
  extraction_id TEXT REFERENCES social_event_extractions(extraction_id) ON DELETE SET NULL,
  event_id TEXT,
  asset TEXT,
  event_type TEXT NOT NULL,
  source TEXT,
  first_seen_at_ms INTEGER NOT NULL,
  last_seen_at_ms INTEGER NOT NULL,
  direction INTEGER NOT NULL,
  impact REAL NOT NULL,
  confidence REAL NOT NULL,
  novelty REAL NOT NULL,
  pricedness REAL NOT NULL,
  base_score REAL NOT NULL,
  event_score REAL NOT NULL,
  source_list_json TEXT NOT NULL DEFAULT '[]',
  raw_event_ids_json TEXT NOT NULL DEFAULT '[]',
  representative_text TEXT NOT NULL,
  risks_json TEXT NOT NULL DEFAULT '[]',
  created_at_ms INTEGER NOT NULL,
  updated_at_ms INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_event_clusters_asset_seen ON event_clusters(asset, first_seen_at_ms);
CREATE INDEX IF NOT EXISTS idx_event_clusters_type_seen ON event_clusters(event_type, first_seen_at_ms);

CREATE TABLE IF NOT EXISTS harness_snapshots (
  snapshot_id TEXT PRIMARY KEY,
  source_event_id TEXT,
  seed_id TEXT REFERENCES attention_seeds(seed_id) ON DELETE SET NULL,
  asset TEXT NOT NULL,
  decision_time_ms INTEGER NOT NULL,
  horizon TEXT NOT NULL,
  combined_score REAL NOT NULL,
  policy_signal TEXT NOT NULL,
  shadow_signal TEXT NOT NULL,
  market_state_json TEXT NOT NULL,
  event_clusters_json TEXT NOT NULL,
  versions_json TEXT NOT NULL,
  config_version TEXT NOT NULL,
  outcome_status TEXT NOT NULL DEFAULT 'pending',
  credit_status TEXT NOT NULL DEFAULT 'none',
  risks_json TEXT NOT NULL DEFAULT '[]',
  created_at_ms INTEGER NOT NULL,
  UNIQUE(source_event_id, asset, horizon, config_version)
);

CREATE INDEX IF NOT EXISTS idx_harness_snapshots_decision ON harness_snapshots(decision_time_ms);
CREATE INDEX IF NOT EXISTS idx_harness_snapshots_asset_horizon ON harness_snapshots(asset, horizon, decision_time_ms);
CREATE INDEX IF NOT EXISTS idx_harness_snapshots_status ON harness_snapshots(outcome_status, horizon, decision_time_ms);

CREATE TABLE IF NOT EXISTS harness_decisions (
  decision_id TEXT PRIMARY KEY,
  snapshot_id TEXT NOT NULL REFERENCES harness_snapshots(snapshot_id) ON DELETE CASCADE,
  asset TEXT NOT NULL,
  decision_time_ms INTEGER NOT NULL,
  execution_mode TEXT NOT NULL,
  signal TEXT NOT NULL,
  side TEXT NOT NULL,
  size REAL NOT NULL DEFAULT 0,
  entry_price REAL,
  risk_reject_reason TEXT,
  config_version TEXT NOT NULL,
  created_at_ms INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_harness_decisions_snapshot ON harness_decisions(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_harness_decisions_mode_time ON harness_decisions(execution_mode, decision_time_ms);

CREATE TABLE IF NOT EXISTS harness_outcomes (
  snapshot_id TEXT PRIMARY KEY REFERENCES harness_snapshots(snapshot_id) ON DELETE CASCADE,
  settled_at_ms INTEGER NOT NULL,
  actual_return REAL NOT NULL,
  expected_return REAL NOT NULL,
  abnormal_return REAL NOT NULL,
  realized_vol REAL NOT NULL,
  normalized_outcome REAL NOT NULL,
  baseline_version TEXT NOT NULL,
  fees REAL NOT NULL DEFAULT 0,
  slippage REAL NOT NULL DEFAULT 0,
  created_at_ms INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_harness_outcomes_settled ON harness_outcomes(settled_at_ms);

CREATE TABLE IF NOT EXISTS harness_credits (
  credit_id TEXT PRIMARY KEY,
  snapshot_id TEXT NOT NULL REFERENCES harness_snapshots(snapshot_id) ON DELETE CASCADE,
  cluster_id TEXT NOT NULL,
  asset TEXT NOT NULL,
  event_type TEXT NOT NULL,
  source TEXT NOT NULL,
  horizon TEXT NOT NULL,
  event_score REAL NOT NULL,
  responsibility REAL NOT NULL,
  credit REAL NOT NULL,
  created_at_ms INTEGER NOT NULL,
  UNIQUE(snapshot_id, cluster_id)
);

CREATE INDEX IF NOT EXISTS idx_harness_credits_created ON harness_credits(created_at_ms);
CREATE INDEX IF NOT EXISTS idx_harness_credits_asset_horizon ON harness_credits(asset, horizon, created_at_ms);

CREATE TABLE IF NOT EXISTS harness_weights (
  key TEXT PRIMARY KEY,
  weight_type TEXT NOT NULL,
  asset TEXT,
  horizon TEXT NOT NULL,
  n INTEGER NOT NULL,
  mean_credit REAL NOT NULL,
  weight REAL NOT NULL,
  status TEXT NOT NULL,
  updated_at_ms INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_harness_weights_type_horizon ON harness_weights(weight_type, horizon);

CREATE TABLE IF NOT EXISTS notifications (
  notification_id TEXT PRIMARY KEY,
  dedup_key TEXT NOT NULL UNIQUE,
  rule_id TEXT NOT NULL,
  severity TEXT NOT NULL,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  entity_type TEXT,
  entity_key TEXT,
  author_handle TEXT,
  symbol TEXT,
  chain TEXT,
  address TEXT,
  event_id TEXT,
  source_table TEXT NOT NULL,
  source_id TEXT NOT NULL,
  occurrence_count INTEGER NOT NULL DEFAULT 1,
  first_seen_at_ms INTEGER NOT NULL,
  last_seen_at_ms INTEGER NOT NULL,
  payload_json TEXT NOT NULL DEFAULT '{}',
  channels_json TEXT NOT NULL DEFAULT '["in_app"]',
  created_at_ms INTEGER NOT NULL,
  updated_at_ms INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_notifications_last_seen
  ON notifications(last_seen_at_ms DESC, created_at_ms DESC);
CREATE INDEX IF NOT EXISTS idx_notifications_rule_seen
  ON notifications(rule_id, last_seen_at_ms DESC);
CREATE INDEX IF NOT EXISTS idx_notifications_entity_seen
  ON notifications(entity_type, entity_key, last_seen_at_ms DESC);
CREATE INDEX IF NOT EXISTS idx_notifications_author_seen
  ON notifications(author_handle, last_seen_at_ms DESC);
CREATE INDEX IF NOT EXISTS idx_notifications_source
  ON notifications(source_table, source_id);

CREATE TABLE IF NOT EXISTS notification_reads (
  notification_id TEXT NOT NULL REFERENCES notifications(notification_id) ON DELETE CASCADE,
  subscriber_key TEXT NOT NULL,
  read_at_ms INTEGER NOT NULL,
  PRIMARY KEY(notification_id, subscriber_key)
);

CREATE INDEX IF NOT EXISTS idx_notification_reads_subscriber
  ON notification_reads(subscriber_key, read_at_ms DESC);

CREATE TABLE IF NOT EXISTS notification_deliveries (
  delivery_id TEXT PRIMARY KEY,
  notification_id TEXT NOT NULL REFERENCES notifications(notification_id) ON DELETE CASCADE,
  channel_id TEXT NOT NULL,
  provider TEXT NOT NULL,
  status TEXT NOT NULL,
  attempt_count INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 5,
  next_run_at_ms INTEGER NOT NULL,
  last_attempt_at_ms INTEGER,
  delivered_at_ms INTEGER,
  last_error TEXT,
  created_at_ms INTEGER NOT NULL,
  updated_at_ms INTEGER NOT NULL,
  UNIQUE(notification_id, channel_id)
);

CREATE INDEX IF NOT EXISTS idx_notification_deliveries_status_next
  ON notification_deliveries(status, next_run_at_ms, created_at_ms);
CREATE INDEX IF NOT EXISTS idx_notification_deliveries_notification
  ON notification_deliveries(notification_id);

CREATE TABLE IF NOT EXISTS account_profiles (
  handle TEXT PRIMARY KEY,
  first_seen_ms INTEGER NOT NULL,
  latest_seen_ms INTEGER NOT NULL,
  follower_max INTEGER,
  watched_status TEXT NOT NULL,
  created_at_ms INTEGER NOT NULL,
  updated_at_ms INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS account_token_call_stats (
  handle TEXT NOT NULL,
  token_id TEXT NOT NULL,
  first_mention_ms INTEGER NOT NULL,
  mention_count INTEGER NOT NULL,
  was_early_author INTEGER NOT NULL,
  price_change_5m_pct REAL,
  price_change_1h_pct REAL,
  price_change_24h_pct REAL,
  max_drawdown_1h_pct REAL,
  outcome_status TEXT NOT NULL,
  updated_at_ms INTEGER NOT NULL,
  PRIMARY KEY(handle, token_id)
);

CREATE INDEX IF NOT EXISTS idx_account_token_call_stats_token
  ON account_token_call_stats(token_id, first_mention_ms);

CREATE TABLE IF NOT EXISTS account_quality_snapshots (
  snapshot_id TEXT PRIMARY KEY,
  handle TEXT NOT NULL,
  window TEXT NOT NULL,
  precision_score REAL,
  early_call_score REAL,
  spam_risk_score REAL,
  avg_realized_return REAL,
  sample_size INTEGER NOT NULL,
  updated_at_ms INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_account_quality_snapshots_handle_window
  ON account_quality_snapshots(handle, window, updated_at_ms DESC);
"""

def migrate(conn: sqlite3.Connection) -> None:
    ensure_fts5_available(conn)
    current_version = _current_schema_version(conn)
    if _should_reset_schema(conn, current_version=current_version):
        _reset_app_schema(conn)
        current_version = 0
    conn.executescript(SCHEMA_SQL)
    _apply_incremental_migrations(conn, current_version=current_version)
    conn.execute("DROP TABLE IF EXISTS token_windows")
    conn.execute("DELETE FROM schema_migrations WHERE version != ?", (SCHEMA_VERSION,))
    conn.execute(
        """
        INSERT INTO schema_migrations(version, name, applied_at_ms)
        VALUES (?, ?, ?)
        ON CONFLICT(version) DO UPDATE SET
          name = excluded.name,
          applied_at_ms = excluded.applied_at_ms
        """,
        (SCHEMA_VERSION, "production_notifications", _now_ms()),
    )
    conn.commit()


def _current_schema_version(conn: sqlite3.Connection) -> int:
    existing = _existing_tables(conn)
    if "schema_migrations" not in existing:
        return 0
    row = conn.execute("SELECT max(version) AS version FROM schema_migrations").fetchone()
    return int(row["version"]) if row and row["version"] is not None else 0


def _should_reset_schema(conn: sqlite3.Connection, *, current_version: int) -> bool:
    existing = _existing_tables(conn)
    if "schema_migrations" not in existing:
        return any(name in existing for name in (*APP_TABLES, *LEGACY_TABLES) if name != "schema_migrations")
    if any(name in existing for name in LEGACY_TABLES):
        return True
    if current_version in {8, 9}:
        return _required_columns_missing(conn)
    if current_version == 11:
        return _required_columns_missing(conn)
    if current_version != SCHEMA_VERSION:
        return True
    return _required_columns_missing(conn)


def _apply_incremental_migrations(conn: sqlite3.Connection, *, current_version: int) -> None:
    if current_version == 8:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS token_market_observations (
              observation_id TEXT PRIMARY KEY,
              attribution_id TEXT NOT NULL REFERENCES event_token_attributions(attribution_id) ON DELETE CASCADE,
              event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
              token_id TEXT NOT NULL REFERENCES tokens(token_id) ON DELETE CASCADE,
              chain TEXT NOT NULL,
              address TEXT NOT NULL,
              symbol TEXT NOT NULL,
              target_received_at_ms INTEGER NOT NULL,
              status TEXT NOT NULL,
              priority INTEGER NOT NULL DEFAULT 100,
              provider TEXT,
              source_channel TEXT NOT NULL DEFAULT 'gmgn_openapi_token_info',
              snapshot_id TEXT,
              attempt_count INTEGER NOT NULL DEFAULT 0,
              max_attempts INTEGER NOT NULL DEFAULT 5,
              next_run_at_ms INTEGER NOT NULL,
              last_error TEXT,
              created_at_ms INTEGER NOT NULL,
              updated_at_ms INTEGER NOT NULL,
              UNIQUE(attribution_id)
            );

            CREATE INDEX IF NOT EXISTS idx_token_market_observations_status_next
              ON token_market_observations(status, next_run_at_ms, priority);
            CREATE INDEX IF NOT EXISTS idx_token_market_observations_token_target
              ON token_market_observations(token_id, target_received_at_ms);
            CREATE INDEX IF NOT EXISTS idx_token_market_observations_event
              ON token_market_observations(event_id);
            """
        )


def _required_columns_missing(conn: sqlite3.Connection) -> bool:
    existing = _existing_tables(conn)
    for table, required in REQUIRED_COLUMNS.items():
        if table not in existing:
            return True
        columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({_quote_identifier(table)})").fetchall()}
        if not required.issubset(columns):
            return True
    return False


def _reset_app_schema(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys=OFF")
    try:
        existing = _existing_tables(conn)
        if "event_fts" in existing:
            conn.execute("DROP TABLE IF EXISTS event_fts")
            existing = _existing_tables(conn)
        for table in reversed((*APP_TABLES, *LEGACY_TABLES)):
            if table != "event_fts" and table in existing:
                conn.execute(f"DROP TABLE IF EXISTS {_quote_identifier(table)}")
        for table in sorted(name for name in _existing_tables(conn) if name.startswith("event_fts_")):
            conn.execute(f"DROP TABLE IF EXISTS {_quote_identifier(table)}")
    finally:
        conn.execute("PRAGMA foreign_keys=ON")


def _existing_tables(conn: sqlite3.Connection) -> set[str]:
    return {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table', 'virtual table')"
        ).fetchall()
    }


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def ensure_fts5_available(conn: sqlite3.Connection) -> None:
    try:
        conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS __fts5_probe USING fts5(value)")
        conn.execute("DROP TABLE IF EXISTS __fts5_probe")
    except sqlite3.OperationalError as exc:
        raise RuntimeError("SQLite FTS5 is required") from exc


def _now_ms() -> int:
    return int(time.time() * 1000)
