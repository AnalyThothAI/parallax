from __future__ import annotations

import sqlite3
import time

SCHEMA_VERSION = 1

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

CREATE TABLE IF NOT EXISTS account_keyword_alerts (
  alert_id TEXT PRIMARY KEY,
  event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
  author_handle TEXT NOT NULL,
  keyword TEXT NOT NULL,
  is_first_seen_global INTEGER NOT NULL,
  is_first_seen_by_author INTEGER NOT NULL,
  received_at_ms INTEGER NOT NULL,
  created_at_ms INTEGER NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_account_keyword_alert_event_keyword
  ON account_keyword_alerts(event_id, keyword);
CREATE INDEX IF NOT EXISTS idx_account_keyword_alerts_received ON account_keyword_alerts(received_at_ms);
CREATE INDEX IF NOT EXISTS idx_account_keyword_alerts_author_received
  ON account_keyword_alerts(author_handle, received_at_ms);

CREATE TABLE IF NOT EXISTS token_windows (
  window_id TEXT PRIMARY KEY,
  entity_key TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  normalized_value TEXT NOT NULL,
  chain TEXT,
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

CREATE UNIQUE INDEX IF NOT EXISTS ux_token_windows_entity_window_start
  ON token_windows(entity_key, window, window_start_ms);
CREATE INDEX IF NOT EXISTS idx_token_windows_window_end ON token_windows(window, window_end_ms);

CREATE TABLE IF NOT EXISTS keyword_windows (
  window_id TEXT PRIMARY KEY,
  keyword TEXT NOT NULL,
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

CREATE UNIQUE INDEX IF NOT EXISTS ux_keyword_windows_keyword_window_start
  ON keyword_windows(keyword, window, window_start_ms);
CREATE INDEX IF NOT EXISTS idx_keyword_windows_window_end ON keyword_windows(window, window_end_ms);
"""


def migrate(conn: sqlite3.Connection) -> None:
    ensure_fts5_available(conn)
    conn.executescript(SCHEMA_SQL)
    conn.execute(
        "INSERT OR IGNORE INTO schema_migrations(version, name, applied_at_ms) VALUES (?, ?, ?)",
        (SCHEMA_VERSION, "evidence_entity_signal_core", _now_ms()),
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
