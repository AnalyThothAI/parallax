from __future__ import annotations

import sqlite3
import time

SCHEMA_VERSION = 6

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

CREATE TABLE IF NOT EXISTS event_enrichments (
  event_id TEXT PRIMARY KEY REFERENCES events(event_id) ON DELETE CASCADE,
  run_id TEXT NOT NULL REFERENCES model_runs(run_id) ON DELETE CASCADE,
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  summary TEXT NOT NULL,
  stance TEXT NOT NULL,
  intent TEXT NOT NULL,
  confidence REAL NOT NULL,
  raw_response_json TEXT NOT NULL,
  created_at_ms INTEGER NOT NULL,
  updated_at_ms INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS event_token_candidates (
  candidate_id TEXT PRIMARY KEY,
  event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
  symbol TEXT,
  project_name TEXT,
  chain TEXT,
  address TEXT,
  evidence TEXT NOT NULL,
  confidence REAL NOT NULL,
  resolution_status TEXT NOT NULL,
  created_at_ms INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_event_token_candidates_symbol
  ON event_token_candidates(symbol, created_at_ms);

CREATE TABLE IF NOT EXISTS event_narratives (
  narrative_id TEXT PRIMARY KEY,
  event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
  narrative_label TEXT NOT NULL,
  description TEXT NOT NULL,
  evidence TEXT NOT NULL,
  confidence REAL NOT NULL,
  stance TEXT NOT NULL,
  intent TEXT NOT NULL,
  received_at_ms INTEGER NOT NULL,
  author_handle TEXT,
  is_watched INTEGER NOT NULL DEFAULT 0,
  created_at_ms INTEGER NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_event_narratives_event_label
  ON event_narratives(event_id, narrative_label);
CREATE INDEX IF NOT EXISTS idx_event_narratives_label_received
  ON event_narratives(narrative_label, received_at_ms);
CREATE INDEX IF NOT EXISTS idx_event_narratives_watched_received
  ON event_narratives(is_watched, received_at_ms);

CREATE TABLE IF NOT EXISTS account_narrative_alerts (
  alert_id TEXT PRIMARY KEY,
  event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
  author_handle TEXT NOT NULL,
  narrative_label TEXT NOT NULL,
  stance TEXT NOT NULL,
  intent TEXT NOT NULL,
  confidence REAL NOT NULL,
  summary TEXT NOT NULL,
  evidence TEXT NOT NULL,
  is_first_seen_global INTEGER NOT NULL,
  is_first_seen_by_author INTEGER NOT NULL,
  received_at_ms INTEGER NOT NULL,
  created_at_ms INTEGER NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_account_narrative_alert_event_label
  ON account_narrative_alerts(event_id, narrative_label);
CREATE INDEX IF NOT EXISTS idx_account_narrative_alerts_received
  ON account_narrative_alerts(received_at_ms);
CREATE INDEX IF NOT EXISTS idx_account_narrative_alerts_author_received
  ON account_narrative_alerts(author_handle, received_at_ms);

CREATE TABLE IF NOT EXISTS narrative_windows (
  window_id TEXT PRIMARY KEY,
  narrative_label TEXT NOT NULL,
  window TEXT NOT NULL,
  window_start_ms INTEGER NOT NULL,
  window_end_ms INTEGER NOT NULL,
  mention_count INTEGER NOT NULL,
  watched_mention_count INTEGER NOT NULL,
  unique_author_count INTEGER NOT NULL,
  weighted_reach REAL NOT NULL,
  market_mindshare REAL NOT NULL,
  watched_mindshare REAL NOT NULL,
  velocity REAL NOT NULL,
  top_authors_json TEXT NOT NULL DEFAULT '[]',
  top_events_json TEXT NOT NULL DEFAULT '[]',
  created_at_ms INTEGER NOT NULL,
  updated_at_ms INTEGER NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_narrative_windows_label_window_start
  ON narrative_windows(narrative_label, window, window_start_ms);
CREATE INDEX IF NOT EXISTS idx_narrative_windows_window_end
  ON narrative_windows(window, window_end_ms);

CREATE TABLE IF NOT EXISTS narrative_seeds (
  seed_id TEXT PRIMARY KEY,
  event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
  narrative_label TEXT NOT NULL,
  seed_family TEXT,
  seed_terms_json TEXT NOT NULL DEFAULT '[]',
  market_interpretation TEXT NOT NULL DEFAULT '',
  stance TEXT NOT NULL,
  intent TEXT NOT NULL,
  confidence REAL NOT NULL,
  source_weight REAL NOT NULL,
  novelty_status TEXT NOT NULL,
  received_at_ms INTEGER NOT NULL,
  author_handle TEXT NOT NULL,
  evidence TEXT NOT NULL,
  summary TEXT NOT NULL,
  created_at_ms INTEGER NOT NULL,
  updated_at_ms INTEGER NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_narrative_seeds_event_label
  ON narrative_seeds(event_id, narrative_label);
CREATE INDEX IF NOT EXISTS idx_narrative_seeds_received
  ON narrative_seeds(received_at_ms);
CREATE INDEX IF NOT EXISTS idx_narrative_seeds_label_received
  ON narrative_seeds(narrative_label, received_at_ms);
CREATE INDEX IF NOT EXISTS idx_narrative_seeds_author_received
  ON narrative_seeds(author_handle, received_at_ms);

CREATE TABLE IF NOT EXISTS narrative_token_links (
  link_id TEXT PRIMARY KEY,
  seed_id TEXT NOT NULL REFERENCES narrative_seeds(seed_id) ON DELETE CASCADE,
  narrative_label TEXT NOT NULL,
  token_identity_key TEXT NOT NULL,
  token_id TEXT,
  identity_status TEXT NOT NULL,
  chain TEXT,
  address TEXT,
  symbol TEXT NOT NULL,
  first_linked_event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
  best_evidence_event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
  link_reason TEXT NOT NULL,
  matched_terms_json TEXT NOT NULL DEFAULT '[]',
  link_confidence REAL NOT NULL,
  lag_ms INTEGER NOT NULL,
  window TEXT NOT NULL,
  mention_count_after_seed INTEGER NOT NULL,
  watched_mention_count_after_seed INTEGER NOT NULL,
  unique_author_count_after_seed INTEGER NOT NULL,
  weighted_reach_after_seed REAL NOT NULL,
  market_cap REAL,
  market_status TEXT NOT NULL,
  price_change_after_seed_pct REAL,
  seed_score INTEGER NOT NULL,
  diffusion_score INTEGER NOT NULL,
  token_link_score INTEGER NOT NULL,
  tradeability_score INTEGER NOT NULL,
  decision TEXT NOT NULL,
  reasons_json TEXT NOT NULL DEFAULT '[]',
  risks_json TEXT NOT NULL DEFAULT '[]',
  created_at_ms INTEGER NOT NULL,
  updated_at_ms INTEGER NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_narrative_token_links_seed_token_window
  ON narrative_token_links(seed_id, token_identity_key, window);
CREATE INDEX IF NOT EXISTS idx_narrative_token_links_label_decision
  ON narrative_token_links(narrative_label, decision, updated_at_ms);
CREATE INDEX IF NOT EXISTS idx_narrative_token_links_token
  ON narrative_token_links(token_identity_key, updated_at_ms);
CREATE INDEX IF NOT EXISTS idx_narrative_token_links_token_id_updated
  ON narrative_token_links(token_id, updated_at_ms);
CREATE INDEX IF NOT EXISTS idx_narrative_token_links_chain_address_updated
  ON narrative_token_links(chain, lower(address), updated_at_ms);
CREATE INDEX IF NOT EXISTS idx_narrative_token_links_symbol_updated
  ON narrative_token_links(symbol, updated_at_ms);
"""

def migrate(conn: sqlite3.Connection) -> None:
    ensure_fts5_available(conn)
    conn.executescript(SCHEMA_SQL)
    conn.execute("DROP TABLE IF EXISTS token_windows")
    conn.execute(
        "INSERT OR IGNORE INTO schema_migrations(version, name, applied_at_ms) VALUES (?, ?, ?)",
        (SCHEMA_VERSION, "rolling_token_radar", _now_ms()),
    )
    conn.commit()


def ensure_fts5_available(conn: sqlite3.Connection) -> None:
    try:
        conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS __fts5_probe USING fts5(value)")
        conn.execute("DROP TABLE IF EXISTS __fts5_probe")
    except sqlite3.OperationalError as exc:
        raise RuntimeError("SQLite FTS5 is required") from exc


def _now_ms() -> int:
    return int(time.time() * 1000)
